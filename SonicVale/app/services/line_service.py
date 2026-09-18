from __future__ import annotations
import contextlib
from app.services.speech import routing as speech_routing
import hashlib
import json
import logging
import re

import shutil
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy import Sequence


from app.core.audio_engin import AudioProcessor
from app.core.config import getConfigPath, getFfmpegPath
from app.core.subtitle import subtitle_engine
from app.core.tts_engine import ConfigurableCloudTTSEngine, EdgeTTSEngine, TTSEngine
from app.core.tts_capabilities import cosyvoice_instruction_mode
from app.core.tts_guidance import build_voice_instruction, edge_prosody
from app.dto.line_dto import LineCreateDTO, LineOrderDTO, LineAudioProcessDTO, LineAudioVariantDTO
from app.entity.line_entity import LineEntity
from app.core.sound_tags import infer_tags
from app.models.po import LinePO, RolePO
from app.repositories.line_repository import LineRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.core.llm_engine import LLMEngine
from app.services.timeline_service import TimelineService
from app.services.audio_selection import selected_audio_path
from app.integrations.audio import transforms as audio_transforms

import os

import numpy as np
import soundfile as sf

PLACEHOLDER_MATERIAL_MARKER = "[AURALIS_PLACEHOLDER_MATERIAL]"

def _lock_key(path: str) -> str:
    return hashlib.md5(path.encode("utf-8")).hexdigest()
_file_locks = defaultdict(threading.Lock)
class LineService:

    def __init__(self, repository: LineRepository,role_repository: RoleRepository,tts_provider_repository: TTSProviderRepository, llm_provider_repository: LLMProviderRepository = None):
        """注入 repository"""

        self.tts_provider_repository = tts_provider_repository
        self.llm_provider_repository = llm_provider_repository
        self.role_repository = role_repository
        self.repository = repository

    def _invalidate_timeline(self, line_id: int, reason: str = "台词或音频版本已变化") -> None:
        db = getattr(self.repository, "db", None)
        if db is not None:
            TimelineService.invalidate_line(db, line_id, reason)

    def create_line(self,  entity: LineEntity):
        """创建新台词
        - 如果存在，抛出异常或返回错误
        - 调用 repository.create 插入数据库
        """
        # 手动将entity转化为po
        po = LinePO(**entity.__dict__)
        if isinstance(self.repository,LineRepository):
            from app.models.po import ChapterPO
            chapter=self.repository.db.get(ChapterPO,po.chapter_id)
            role=self.role_repository.get_by_id(po.role_id) if po.role_id else None
            if not chapter or (po.role_id and (not role or role.project_id!=chapter.project_id)):
                raise ValueError('章节或角色归属无效')
        res = self.repository.create(po)

        # res(po) --> entity
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        entity = LineEntity(**data)

        # 将po转化为entity
        return entity


    def get_line(self, line_id: int) -> LineEntity | None:
        """根据 ID 查询台词"""
        po = self.repository.get_by_id(line_id)
        if not po:
            return None
        data = {k: v for k, v in po.__dict__.items() if not k.startswith("_")}
        if isinstance(self.repository,LineRepository):
            from app.services.production.audio_state import generation_state
            if generation_state(self.repository.db,po)['input_current'] is False:
                data.update(status='pending',is_done=0)
        res = LineEntity(**data)
        return res

    def get_all_lines(self,chapter_id: int) -> Sequence[LineEntity]:
        """获取所有台词列表"""
        pos = self.repository.get_all(chapter_id)
        # pos -> entities

        entities = [self.get_line(po.id) for po in pos]
        return entities

    def delete_line(self, line_id: int) -> bool:
        """Remove a script row while retaining its takes and an audit snapshot."""
        from pathlib import Path
        from sqlalchemy import delete, update
        from app.models.po import AudioAssetPO, AudioTaskPO, TimelineClipPO, TimelineTrackPO

        line = self.repository.get_by_id(line_id)
        if line is None:
            return False
        db = self.repository.db
        tasks = db.query(AudioTaskPO).filter(AudioTaskPO.line_id == line_id).all()
        if line.status == "processing" or any(task.status in {"queued", "processing", "completing"} for task in tasks):
            raise ValueError("本句正在等待或生成音频，请任务结束后再删除")
        serialize = lambda row: {column.name: getattr(row, column.name) for column in row.__table__.columns}
        clips = db.query(TimelineClipPO).filter(TimelineClipPO.chapter_id == line.chapter_id).all()
        anchored = []
        for other in self.repository.get_all(line.chapter_id):
            cue = TimelineService.sound_library_cue(other)
            if other.id != line_id and cue and cue.get("anchor_line_id") == line_id:
                anchored.append((other, cue))
        history = Path(getConfigPath()) / "deleted_lines"
        history.mkdir(parents=True, exist_ok=True)
        (history / f"{line_id}-{uuid4().hex}.json").write_text(json.dumps({
            "line": serialize(line), "tasks": [serialize(task) for task in tasks],
            "clips": [serialize(clip) for clip in clips if clip.line_id == line_id],
            "anchored_lines": [serialize(other) for other, _ in anchored],
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            # Keep attached ambience at its last actual position after its anchor
            # disappears, instead of silently dropping it on the next rebuild.
            for other, cue in anchored:
                placed = next((clip for clip in clips if clip.line_id == other.id), None)
                updated = dict(cue, anchor_line_id=None, placement="with",
                               offset_ms=placed.start_ms if placed else 0)
                other.audio_events = [updated if event == cue else event
                                      for event in TimelineService._items(other.audio_events)]
            db.execute(delete(TimelineClipPO).where(TimelineClipPO.line_id == line_id))
            db.execute(update(AudioAssetPO).where(AudioAssetPO.line_id == line_id).values(line_id=None))
            db.execute(delete(AudioTaskPO).where(AudioTaskPO.line_id == line_id))
            db.execute(update(TimelineTrackPO).where(TimelineTrackPO.chapter_id == line.chapter_id)
                       .values(status="stale", last_error="台词已删除，请刷新时间线"))
            remaining = [other for other in self.repository.get_all(line.chapter_id) if other.id != line_id]
            for order, other in enumerate(remaining, 1):
                other.line_order = order
            db.delete(line)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return True

    # 删除章节下所有台词
    def delete_all_lines(self, chapter_id: int) -> bool:
        """删除章节下所有台词
        """
        from app.services.production.chapter_lifecycle import prepare_removal
        db = self.repository.db
        try:
            prepare_removal(db, chapter_id)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise

    # 单个台词新增
    def add_new_line(self, line: LineCreateDTO,project_id,chapter_id,index,emotions_dict, strengths_dict,audio_path):
    #     先判断角色是否存在
        role = self.role_repository.get_by_name(line.role_name,project_id)
        if role is None:
            #         新增角色
            role = self.role_repository.create(RolePO(name=line.role_name, project_id=project_id))
        # 获取情绪id
        emotion_id = emotions_dict.get(line.emotion_name)
        # 获取强度id
        strength_id = strengths_dict.get(line.strength_name)
        res = self.repository.create(LinePO(text_content=line.text_content, role_id=role.id,
                                           chapter_id=chapter_id,line_order = index+1,emotion_id=emotion_id,strength_id=strength_id))

        # 新增台词,这里搞个audio_path

        # audio_path = os.path.join(getConfigPath(), str(project_id), str(chapter_id), "audio")
        # os.makedirs(audio_path, exist_ok=True)
        res_path = os.path.join(audio_path, "id_"+str(res.id) + ".wav")
        self.repository.update(res.id, {"audio_path": res_path})


    def update_init_lines(self, lines: list, project_id: object, chapter_id: object,emotions_dict, strengths_dict,audio_path) -> None:
        for index, line in enumerate(lines):
            self.add_new_line(line,project_id,chapter_id,index,emotions_dict, strengths_dict,audio_path)

    # 获取章节下所有台词

    # 更新line
    def update_line(self, line_id: int, data: dict) -> bool:
        from app.services.production.line_commands import LineCommands
        if isinstance(self.repository, LineRepository):
            return LineCommands(self.repository).update(line_id, data)
        # Legacy test/integration repository adapter; production uses LineCommands.
        po = self.repository.get_by_id(line_id)
        if po is None:
            return False
        if getattr(po,"track",None) in {"sfx", "bgm"} and "sound_tags" not in data and any(k in data for k in ("sound_prompt", "text_content")):
            data = {**data, "sound_tags": infer_tags(data.get("sound_prompt") or data.get("text_content") or po.sound_prompt)}
        generation_fields = {"text_content", "production_note", "emotion_id", "strength_id", "voice_id"}
        changed = any(key in data and data[key] != getattr(po, key, None) for key in generation_fields)
        if changed and po.should_speak != 0 and po.track not in {"sfx", "bgm"}:
            data = {**data, "status": "pending", "is_done": 0}
        res = self.repository.update(line_id, data)
        if res is None:
            return False
        self._invalidate_timeline(line_id)
        return True
    # 生成音频（服务器和本地两种方式）

    def resolve_tts_route(self, role=None, line_type: str | None = None, track: str | None = None, emotion_name: str | None = None) -> str:
        return speech_routing.resolve_tts_route(role,line_type,track,emotion_name)

    def generate_audio(
        self,
        reference_path: str,
        tts_provider_id,
        content,
        emo_text: str,
        emo_vector: list[float],
        save_path=None,
        role=None,
        voice=None,
        line_type: str | None = None,
        track: str | None = None,
        emotion_name: str | None = None,
        strength_name: str | None = None,
        production_note: str | None = None,
        speech_context: dict | None = None,
        request_observer=None,
    ):
        content = speech_context["tts_text"] if speech_context else self.clean_tts_text(content)
        if not content:
            raise ValueError("可朗读文本清洗后为空，请把音效提示移到声音事件或制作备注")
        route = self.resolve_tts_route(role, line_type=line_type, track=track, emotion_name=emotion_name)
        provider = self.tts_provider_repository.get_by_id(tts_provider_id) if self.tts_provider_repository and tts_provider_id else None
        mode, compact = "native", False
        model = str(getattr(provider, "model", None) or "").lower()
        if model.startswith("cosyvoice"):
            params = ConfigurableCloudTTSEngine._parse_params(getattr(provider, "custom_params", None))
            mode = cosyvoice_instruction_mode(model, params, self.resolve_cosyvoice_voice(voice))
            compact = mode == "native"
        voice_instruction = build_voice_instruction(
            emotion_name, strength_name, production_note, mode=mode, compact=compact,
        )
        if speech_context:
            voice_instruction = speech_context["instruction"]
            emotion_name = speech_context["emotion"]
            strength_name = speech_context["effective_strength"]
            production_note = speech_context.get("delivery_note", production_note)
            from app.core.tts_guidance import emotion_text_to_vector
            emo_vector = emotion_text_to_vector(emotion_name, strength_name)
        if provider is not None and getattr(provider, "status", 1) == 0:
            raise ValueError("当前角色绑定的配音模型已停用，请选择已启用的音色；已保存配音可继续试听")
        if (getattr(provider, "provider_type", None) or "").lower() == "edge":
            route = "edge"
        if self.resolve_cosyvoice_voice(voice):
            route = "cloud"
        if route == "skip":
            return b""
        if route == "edge":
            return self.generate_edge_audio(
                content,
                save_path,
                role=role,
                voice=voice,
                instruction=voice_instruction,
                emotion_name=emotion_name,
                strength_name=strength_name,
                production_note=production_note,
                request_observer=request_observer,
            )
        return self.generate_cloud_audio(
            reference_path,
            tts_provider_id,
            content,
            emo_text,
            emo_vector,
            save_path,
            voice=voice,
            instruction=voice_instruction,
            provider_overrides=(speech_context or {}).get("provider_overrides"),
            request_observer=request_observer,
        )

    @staticmethod
    def clean_tts_text(content: str | None) -> str:
        from app.services.speech_direction_service import clean_spoken_text
        return clean_spoken_text(content)

    def generate_edge_audio(
        self,
        content,
        save_path=None,
        role=None,
        voice=None,
        instruction: str | None = None,
        emotion_name: str | None = None,
        strength_name: str | None = None,
        production_note: str | None = None,
        request_observer=None,
    ):
        edge_voice = self.resolve_edge_voice(role=role, voice=voice)
        guidance = production_note if production_note is not None else instruction
        prosody = edge_prosody(emotion_name, strength_name, guidance)
        if request_observer:
            request_observer("request", {"driver": "edge", "text": content, "voice": edge_voice, **prosody})
        audio = EdgeTTSEngine().synthesize(
            content,
            save_path=save_path,
            voice=edge_voice,
            rate=prosody["rate"],
            pitch=prosody["pitch"],
            volume=prosody["volume"],
        )
        if request_observer:
            request_observer("response", {"response_kind": "audio", "audio_bytes": len(audio)})
        return audio

    def resolve_edge_voice(self, role=None, voice=None) -> str:
        return speech_routing.resolve_edge_voice(role,voice)

    def generate_cloud_audio(self, reference_path: str,tts_provider_id,content,emo_text:str,emo_vector:list[float],save_path= None, voice=None, instruction: str | None = None, provider_overrides=None, request_observer=None):
        tts_provider = self.tts_provider_repository.get_by_id(tts_provider_id)
        if tts_provider is None:
            raise Exception(f"TTS服务提供商不存在（ID: {tts_provider_id}）")

        provider_type = (getattr(tts_provider, "provider_type", None) or "cloud").lower()
        if provider_type == "edge":
            return self.generate_edge_audio(content, save_path=save_path, voice=voice, instruction=instruction, request_observer=request_observer)

        if not tts_provider.api_base_url:
            raise Exception("TTS服务地址未配置，请先在配置中心设置TTS服务")

        if provider_type not in {"fish", "legacy", "index_tts"}:
            model_name = (getattr(tts_provider, "model", None) or "").lower()
            voice_description = (getattr(voice, "description", None) or "")
            if model_name.startswith("cosyvoice-v3") and "CosyVoice-v1" in voice_description:
                raise ValueError("当前音色属于 CosyVoice-v1，不能用于 v3 指令模型；请重新选择 v3 兼容音色")
            if model_name.startswith(("cosyvoice-v1", "cosyvoice-v2")) and "CosyVoice-v3" in voice_description:
                raise ValueError("当前音色属于 CosyVoice-v3，不能用于 v1/v2 基础模型；请重新选择基础模式音色")
            engine = ConfigurableCloudTTSEngine(
                tts_provider.api_base_url,
                api_key=tts_provider.api_key,
                model=getattr(tts_provider, "model", None),
                custom_params={**ConfigurableCloudTTSEngine._parse_params(getattr(tts_provider, "custom_params", None)), **(provider_overrides or {})},
            )
            engine.observer = request_observer
            voice_name = self.resolve_cosyvoice_voice(voice) or getattr(voice, "name", None)
            return engine.synthesize(
                content,
                save_path=save_path,
                voice_name=voice_name,
                reference_path=reference_path,
                emo_text=emo_text,
                emo_vector=emo_vector,
                instruction=instruction,
            )

        tts_engine = TTSEngine(tts_provider.api_base_url, api_key=tts_provider.api_key)
        tts_engine.observer = request_observer

        # 检查参考音频路径是否有效
        if not reference_path:
            raise Exception("参考音频路径未设置，请检查角色音色配置")

        key = _lock_key(reference_path)
        lock = _file_locks[key]

        with lock:
            try:
                audio_exists = tts_engine.check_audio_exists(reference_path)
            except Exception as e:
                raise Exception(f"检查参考音频失败: {str(e)}")
            
            if not audio_exists:
                # 检查本地文件是否存在
                if not os.path.isfile(reference_path):
                    raise Exception(f"参考音频文件不存在: {reference_path}")
                
                upload_result = tts_engine.upload_audio(reference_path, reference_path)
                if upload_result.get('code') and upload_result.get('code') != 200:
                    raise Exception(f"上传参考音频失败: {upload_result.get('msg', '未知错误')}")
            
            # The engine records the serialized request and response at the transport boundary.
            audio = tts_engine.synthesize(content, reference_path, emo_text, emo_vector, save_path)
            return audio

    @staticmethod
    def resolve_cosyvoice_voice(voice=None) -> str | None:
        return speech_routing.resolve_cosyvoice_voice(voice)

    # 将角色role_id下所有台词的role_id都置位空
    def clear_role_id(self, role_id: int):
        from app.services.production.line_commands import LineCommands
        return LineCommands(self.repository).clear_role(role_id)

    def batch_update_line_order(self,line_orders:List[LineOrderDTO]):
        from app.services.production.line_commands import LineCommands
        return LineCommands(self.repository).reorder(line_orders)

    def update_audio_path(self, id, dto) -> bool:
        raise ValueError("音频版本路径不可重命名；请使用选用版本或素材导入接口")

    def attach_audio_asset(self, line_id: int, source_path: str) -> str:
        po = self.repository.get_by_id(line_id)
        if po is None:
            raise ValueError("台词不存在")
        if not source_path or not os.path.exists(source_path):
            raise FileNotFoundError(f"素材文件不存在: {source_path}")
        if not os.path.isfile(source_path):
            raise ValueError("请选择音频文件")

        ext = os.path.splitext(source_path)[1].lower()
        if ext not in {".wav", ".mp3", ".m4a", ".ogg", ".flac"}:
            raise ValueError("仅支持 wav/mp3/m4a/ogg/flac 音频素材")

        if po.audio_path:
            target_dir = os.path.dirname(po.audio_path)
        else:
            target_dir = os.path.join(getConfigPath(), "assets", str(po.chapter_id), "audio")
        os.makedirs(target_dir, exist_ok=True)

        # Each selection gets its own copy; reselecting must not overwrite a
        # previously used file that a take or existing render still references.
        target_path = os.path.join(target_dir, f"id_{po.id}_asset_{uuid4().hex[:12]}{ext}")
        if os.path.abspath(source_path) != os.path.abspath(target_path):
            shutil.copy2(source_path, target_path)

        production_note = self._clear_placeholder_note(getattr(po, "production_note", None))
        self.update_line(po.id, {
            "active_audio_version_id": None,
            "active_audio_variant_id": None,
            "audio_path": target_path,
            "status": "done",
            "is_done": 1,
            "subtitle_path": None,
            "production_note": production_note,
            "audio_events": getattr(po, "audio_events", None) or [],
            "audio_variants": getattr(po, "audio_variants", None) or [],
        })
        return target_path

    def _is_placeholder_material(self, line) -> bool:
        note = getattr(line, "production_note", None) or ""
        path = getattr(line, "audio_path", None) or ""
        return PLACEHOLDER_MATERIAL_MARKER in note or "_material_placeholder" in os.path.basename(str(path))

    def _clear_placeholder_note(self, note: str | None) -> str:
        if not note:
            return ""
        lines = [
            item.strip()
            for item in str(note).splitlines()
            if PLACEHOLDER_MATERIAL_MARKER not in item
        ]
        return "\n".join(item for item in lines if item)

    def _convert_audio_to_wav(self, *args, **kwargs):
        return audio_transforms._convert_audio_to_wav(*args, **kwargs)

    def process_audio_ffmpeg(self, *args, **kwargs):
        return audio_transforms.process_audio_ffmpeg(*args, **kwargs)


    # 删除区间进行拼接
    def process_audio_ffmpeg_cut(self, *args, **kwargs):
        return audio_transforms.process_audio_ffmpeg_cut(*args, **kwargs)

    def process_audio(self, line_id, dto: LineAudioProcessDTO):
        """Legacy URL delegates to non-destructive version creation."""
        if not self.repository.get_by_id(line_id):
            return False
        self.create_audio_variant(line_id,LineAudioVariantDTO(**dto.model_dump()))
        return True

    def ensure_generated_audio_version(self, line_id: int) -> dict | None:
        """Archive a legacy source before a regeneration overwrites it."""
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        versions = list(getattr(line, "audio_versions", None) or [])
        if versions:
            active_id = getattr(line, "active_audio_version_id", None)
            return next((item for item in versions if item.get("id") == active_id), versions[-1])
        source_path = os.path.abspath(os.path.expanduser(getattr(line, "audio_path", None) or ""))
        if not source_path or not os.path.isfile(source_path):
            return None
        return self.register_generated_audio_version(line_id, source_path, {"origin": "legacy"})

    def register_generated_audio_version(
        self,
        line_id: int,
        source_path: str,
        metadata: dict | None = None,
    ) -> dict:
        """Copy one TTS result into immutable version storage and make it current."""
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        source_path = os.path.abspath(os.path.expanduser(source_path or ""))
        if not source_path or not os.path.isfile(source_path):
            raise FileNotFoundError("生成音频文件不存在")

        versions = list(getattr(line, "audio_versions", None) or [])
        version_id = uuid4().hex[:12]
        extension = os.path.splitext(source_path)[1].lower() or ".wav"
        version_dir = os.path.join(os.path.dirname(source_path), "generated_versions")
        os.makedirs(version_dir, exist_ok=True)
        target_path = os.path.join(version_dir, f"line_{line_id}_{version_id}{extension}")
        shutil.copy2(source_path, target_path)
        version = {
            "id": version_id,
            "label": f"版本 {len(versions) + 1}",
            "kind": "generated",
            "audio_path": target_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        versions.append(version)
        self.update_line(line_id, {
            "active_audio_variant_id": None,
            "audio_versions": versions,
            "active_audio_version_id": version_id,
        })
        return version

    def get_generated_audio_version(self, line_id: int, version_id: str) -> dict:
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        version = next(
            (item for item in (getattr(line, "audio_versions", None) or []) if item.get("id") == version_id),
            None,
        )
        if not version:
            raise ValueError("生成音频版本不存在")
        return version

    def activate_generated_audio_version(self, line_id: int, version_id: str) -> dict:
        line = self.repository.get_by_id(line_id)
        version = self.get_generated_audio_version(line_id, version_id)
        audio_path = os.path.abspath(os.path.expanduser(version.get("audio_path") or ""))
        if not os.path.isfile(audio_path):
            raise FileNotFoundError("生成音频版本文件不存在")
        self.update_line(line_id, {"active_audio_variant_id": None, "active_audio_version_id": version_id})
        return version

    def create_audio_variant(self, line_id: int, dto: LineAudioVariantDTO) -> dict:
        """Create a non-destructive processed version while preserving the generated source."""
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        source_path = self.resolve_audio_path(line, original=True)
        if not source_path or not os.path.isfile(source_path):
            raise FileNotFoundError("该台词还没有可处理的原始音频")

        variant_id = uuid4().hex[:12]
        variant_dir = os.path.join(os.path.dirname(source_path), "variants")
        os.makedirs(variant_dir, exist_ok=True)
        target_path = os.path.join(variant_dir, f"line_{line_id}_{variant_id}.wav")
        if os.path.splitext(source_path)[1].lower() == ".wav":
            shutil.copy2(source_path, target_path)
        else:
            self._convert_audio_to_wav(source_path, target_path)

        processor = AudioProcessor(target_path)
        speed = float(dto.speed or 1.0)
        region_action = (dto.region_action or "").strip().lower()
        is_local_speed = (
            region_action == "speed"
            and dto.start_ms is not None
            and dto.end_ms is not None
            and dto.end_ms > dto.start_ms
        )
        if is_local_speed:
            processor.change_speed_range(dto.start_ms, dto.end_ms, speed)
        elif dto.start_ms is not None and dto.end_ms is not None and dto.end_ms > dto.start_ms:
            processor.cut(dto.start_ms, dto.end_ms)
        elif dto.current_ms is not None and dto.silence_sec:
            processor.insert_silence(dto.current_ms, dto.silence_sec)
        elif dto.silence_sec:
            processor.append_silence(dto.silence_sec)
        volume = float(dto.volume if dto.volume is not None else 1.0)
        if not is_local_speed and abs(speed - 1.0) > 1e-6:
            processor.change_speed(speed)
        if abs(volume - 1.0) > 1e-6:
            processor.change_volume(volume)

        variant = {
            "id": variant_id,
            "label": (dto.label or "").strip() or (
                f"{speed:g}x 局部变速 {dto.start_ms / 1000:g}–{dto.end_ms / 1000:g}s · {volume:g}x 音量"
                if is_local_speed else f"{speed:g}x 速度 · {volume:g}x 音量"
            ),
            "speed": speed,
            "volume": volume,
            "start_ms": dto.start_ms,
            "end_ms": dto.end_ms,
            "silence_sec": float(dto.silence_sec or 0),
            "current_ms": dto.current_ms,
            "region_action": region_action or None,
            "source_audio_version_id": getattr(line, "active_audio_version_id", None),
            "audio_path": target_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        variants = list(getattr(line, "audio_variants", None) or [])
        variants.append(variant)
        self.update_line(line_id, {
            "audio_variants": variants,
            "active_audio_variant_id": variant_id,
        })
        return variant

    def resolve_audio_path(self, line, original: bool = False) -> str:
        return selected_audio_path(line, original=original)

    def activate_audio_variant(self, line_id: int, variant_id: str) -> dict:
        variant = self.get_audio_variant(line_id, variant_id)
        audio_path = os.path.abspath(os.path.expanduser(variant.get("audio_path") or ""))
        if not os.path.isfile(audio_path):
            raise FileNotFoundError("音频版本文件不存在")
        source=variant.get('source_audio_version_id')
        if source:
            self.get_generated_audio_version(line_id,source)
        changes={'active_audio_variant_id':variant_id}
        if source:changes['active_audio_version_id']=source
        self.update_line(line_id,changes)
        return variant

    def get_audio_variant(self, line_id: int, variant_id: str) -> dict:
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        variant = next((item for item in (line.audio_variants or []) if item.get("id") == variant_id), None)
        if not variant:
            raise ValueError("音频版本不存在")
        return variant

    def delete_audio_variant(self, line_id: int, variant_id: str) -> bool:
        line = self.repository.get_by_id(line_id)
        if not line:
            raise ValueError("台词不存在")
        variants = list(line.audio_variants or [])
        variant = next((item for item in variants if item.get("id") == variant_id), None)
        if not variant:
            raise ValueError("音频版本不存在")
        audio_path = os.path.abspath(os.path.expanduser(variant.get("audio_path") or ""))
        # Removing a selection archives its metadata and retains the file.
        from pathlib import Path
        history=Path(getConfigPath())/'audio_variant_history'
        history.mkdir(parents=True,exist_ok=True)
        (history/f'{line_id}-{variant_id}-{uuid4().hex}.json').write_text(
            json.dumps({'line_id':line_id,'variant':variant},ensure_ascii=False,indent=2),encoding='utf-8')
        updates = {"audio_variants": [item for item in variants if item.get("id") != variant_id]}
        if getattr(line, "active_audio_variant_id", None) == variant_id:
            updates["active_audio_variant_id"] = None
        self.update_line(line_id, updates)
        return True

    # 导出音频,合并音频，并且导出字幕
    def concat_wav_files(self,paths, out_path, verify=True, block_frames=262144):
        """
        按顺序把若干 WAV 合并到 out_path。
        假设：采样率与声道一致（如需更稳，可保留 verify=True 做轻校验）。
        """
        assert paths and len(paths) >= 1, "至少提供一个文件路径"
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        # 以首文件格式为准
        info0 = sf.info(paths[0])
        sr, ch, subtype = info0.samplerate, info0.channels, info0.subtype or "PCM_16"

        # 可选校验
        if verify:
            for p in paths[1:]:
                info = sf.info(p)
                if info.samplerate != sr or info.channels != ch:
                    raise ValueError(
                        f"格式不一致：{p} (sr={info.samplerate}, ch={info.channels}) vs 首文件 (sr={sr}, ch={ch})")

        # 流式写入
        with sf.SoundFile(out_path, mode='w', samplerate=sr, channels=ch, format='WAV', subtype=subtype) as fout:
            for p in paths:
                with sf.SoundFile(p, mode='r') as fin:
                    if verify and (fin.samplerate != sr or fin.channels != ch):
                        raise ValueError(f"参数不一致：{p}")
                    while True:
                        block = fin.read(block_frames, dtype='float32', always_2d=True)
                        if len(block) == 0:
                            break
                        fout.write(block.astype(np.float32, copy=False))
        return out_path



    def _role_name(self, role_id: int | None) -> str:
        if not role_id or not self.role_repository:
            return "素材"
        role = self.role_repository.get_by_id(role_id)
        return role.name if role else "未知角色"

    def _line_manifest_item(self, line) -> dict:
        return {
            "id": line.id,
            "order": line.line_order,
            "scene_title": getattr(line, "scene_title", None),
            "role": self._role_name(line.role_id),
            "text": line.text_content,
            "line_type": getattr(line, "line_type", None) or "dialogue",
            "track": getattr(line, "track", None) or "voice",
            "should_speak": bool(getattr(line, "should_speak", 1)),
            "emotion_id": line.emotion_id,
            "strength_id": line.strength_id,
            "voice_profile": getattr(line, "voice_profile", None),
            "sound_prompt": getattr(line, "sound_prompt", None),
            "sound_tags": getattr(line, "sound_tags", None) or [],
            "production_note": getattr(line, "production_note", None),
            "audio_events": getattr(line, "audio_events", None) or [],
            "audio_versions": getattr(line, "audio_versions", None) or [],
            "active_audio_version_id": getattr(line, "active_audio_version_id", None),
            "audio_variants": getattr(line, "audio_variants", None) or [],
            "active_audio_variant_id": getattr(line, "active_audio_variant_id", None),
            "is_placeholder_material": self._is_placeholder_material(line),
            "audio_path": self.resolve_audio_path(line),
            "subtitle_path": getattr(line, "subtitle_path", None),
            "status": getattr(line, "status", None),
            "is_done": bool(getattr(line, "is_done", 0)),
        }

    def export_production_manifest(self, lines, file_path: str) -> str:
        manifest = {
            "format": "auralis.production_manifest.v1",
            "line_count": len(lines),
            "tracks": {
                "voice": len([line for line in lines if (getattr(line, "track", None) or "voice") == "voice"]),
                "narration": len([line for line in lines if getattr(line, "track", None) == "narration"]),
                "sfx": len([line for line in lines if getattr(line, "track", None) == "sfx"]),
                "bgm": len([line for line in lines if getattr(line, "track", None) == "bgm"]),
            },
            "lines": [self._line_manifest_item(line) for line in lines],
        }
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        return file_path

    def export_lines_to_excel(self,lines, file_path="all_lines.xlsx"):
        # 1) 取出所有数据
        # lines = self.repository.get_all(chapter_id)

        # 2) 创建 Excel 工作簿
        wb = Workbook()
        ws = wb.active
        ws.title = "Lines"

        # 3) 写表头（根据你的数据字段调整）
        headers = [
            "序号",
            "场景",
            "轨道",
            "类型",
            "是否朗读",
            "角色",
            "台词/素材提示",
            "声线建议",
            "音效/BGM提示",
            "制作备注",
            "占位素材",
            "音频路径",
            "状态",
        ]
        ws.append(headers)

        # 4) 写内容
        for line in lines:
            ws.append([
                line.line_order,
                getattr(line, "scene_title", None),
                getattr(line, "track", None) or "voice",
                getattr(line, "line_type", None) or "dialogue",
                "是" if getattr(line, "should_speak", 1) else "否",
                self._role_name(line.role_id),
                line.text_content,
                getattr(line, "voice_profile", None),
                getattr(line, "sound_prompt", None),
                getattr(line, "production_note", None),
                "是" if self._is_placeholder_material(line) else "否",
                line.audio_path,
                getattr(line, "status", None),
            ])
        # 5) 保存到文件
        wb.save(file_path)
        return file_path

    def export_audio(self, chapter_id, single=False):
        """导出音频与字幕
        
        Returns:
            dict: 包含导出结果的详细信息
                - success: bool, 是否成功
                - message: str, 错误信息（如果失败）
                - audio_path: str, 合并后的音频路径
                - subtitle_path: str, 字幕路径
                - missing_files: list, 缺失的音频文件列表
        """
        try:
            # 拿到所有的台词
            lines = self.repository.get_all(chapter_id)
            
            if not lines:
                return {"success": False, "message": "该章节没有台词"}
            
            # 过滤掉空路径和不存在的文件
            valid_lines = []
            missing_files = []
            for line in lines:
                effective_path = self.resolve_audio_path(line)
                if not effective_path:
                    missing_files.append(f"台词#{line.id}(序号{line.line_order}): 无音频路径")
                elif not os.path.exists(effective_path):
                    missing_files.append(f"台词#{line.id}(序号{line.line_order}): 文件不存在 - {effective_path}")
                else:
                    valid_lines.append(line)
            
            if not valid_lines:
                return {
                    "success": False, 
                    "message": "没有有效的音频文件可导出",
                    "missing_files": missing_files
                }
            
            source_paths = [self.resolve_audio_path(line) for line in valid_lines]

            # 把首个有效音频的目录作为导出基准目录
            output_dir_path = os.path.join(os.path.dirname(source_paths[0]), "result")
            # 不存在就创建
            os.makedirs(output_dir_path, exist_ok=True)
            
            # 放到result目录下
            output_path = os.path.join(output_dir_path, "result.wav")
            
            # 合并音频文件
            try:
                with tempfile.TemporaryDirectory(prefix="normalized_", dir=output_dir_path) as tmp_dir:
                    normalized_paths = []
                    for index, path in enumerate(source_paths, start=1):
                        normalized_path = os.path.join(tmp_dir, f"{index:04d}.wav")
                        self._convert_audio_to_wav(path, normalized_path)
                        normalized_paths.append(normalized_path)
                    self.concat_wav_files(normalized_paths, output_path)
            except ValueError as e:
                return {
                    "success": False,
                    "message": f"音频合并失败: {str(e)}",
                    "missing_files": missing_files
                }
            except Exception as e:
                logging.exception("[export_audio] concat_wav_files 失败")
                return {
                    "success": False,
                    "message": f"音频合并异常: {str(e)}",
                    "missing_files": missing_files
                }
            
            # 生成字幕
            output_subtitle_path = os.path.join(output_dir_path, "result.srt")
            try:
                subtitle_engine.generate_subtitle(output_path, output_subtitle_path)
            except Exception as e:
                logging.exception("[export_audio] 生成整体字幕失败")
                # 字幕生成失败不影响音频导出，继续执行
            
            # 生成单条字幕（如果需要）
            if single:
                subtitle_dir_path = os.path.join(os.path.dirname(source_paths[0]), "subtitles")
                # 先清空这个文件夹
                shutil.rmtree(subtitle_dir_path, ignore_errors=True)
                os.makedirs(subtitle_dir_path, exist_ok=True)
                
                for line in valid_lines:
                    try:
                        path = self.resolve_audio_path(line)
                        base_name = os.path.splitext(os.path.basename(path))[0]
                        subtitle_path = os.path.join(subtitle_dir_path, base_name + ".srt")
                        subtitle_engine.generate_subtitle(path, subtitle_path)
                        # 将subtitle_path写进line.subtitle_path
                        self.repository.update(line.id, {"subtitle_path": subtitle_path})
                    except Exception as e:
                        logging.warning(f"[export_audio] 生成单条字幕失败 line#{line.id}: {e}")
                        # 单条字幕失败不影响整体导出
            
            # 导出所有数据到Excel
            excel_path = os.path.join(output_dir_path, "all_lines.xlsx")
            manifest_path = os.path.join(output_dir_path, "production_manifest.json")
            try:
                self.export_lines_to_excel(lines, excel_path)
            except Exception as e:
                logging.warning(f"[export_audio] 导出Excel失败: {e}")
                # Excel导出失败不影响整体导出

            try:
                self.export_production_manifest(lines, manifest_path)
            except Exception as e:
                logging.warning(f"[export_audio] 导出制作清单失败: {e}")
                manifest_path = None
            
            result = {
                "success": True,
                "audio_path": output_path,
                "subtitle_path": output_subtitle_path,
                "excel_path": excel_path,
                "manifest_path": manifest_path,
                "exported_count": len(valid_lines),
                "total_count": len(lines)
            }
            
            if missing_files:
                result["missing_files"] = missing_files
                result["message"] = f"导出成功，但有{len(missing_files)}条台词缺少音频"
            
            return result
            
        except Exception as e:
            logging.exception("[export_audio] 未预期的错误")
            return {"success": False, "message": f"导出失败: {str(e)}"}




    def generate_subtitle(self, line_id, dto):
        # 获取台词
        line = self.get_line(line_id)
        if line:
            # 将音频文件路径的后缀改为.srt
            dto.subtitle_path = os.path.splitext(dto.subtitle_path)[0] + ".srt"
            subtitle_engine.generate_subtitle(line.audio_path,dto.subtitle_path)
            return dto.subtitle_path
        else:
            return None
#     字幕矫正 - 拼音匹配
    def correct_subtitle_pinyin(self, text, output_subtitle_path):
        """
        使用拼音匹配算法矫正字幕
        
        text: 原始正确文本
        output_subtitle_path: 字幕文件路径
        """
        subtitle_engine.correct_srt_file(text, output_subtitle_path)

#     字幕矫正 - LLM
    def correct_subtitle_llm(self, text, output_subtitle_path, llm_provider_id: int, llm_model: str, batch_size: int = 20):
        """
        使用LLM矫正字幕
        
        text: 原始正确文本
        output_subtitle_path: 字幕文件路径
        llm_provider_id: LLM提供商ID
        llm_model: LLM模型名称
        batch_size: 分批处理时每批的条数
        """
        if not self.llm_provider_repository:
            raise Exception("LLM Provider Repository 未配置")
        
        llm_provider = self.llm_provider_repository.get_by_id(llm_provider_id)
        if llm_provider is None:
            raise Exception(f"LLM服务提供商不存在（ID: {llm_provider_id}）")
        
        llm_engine = LLMEngine(
            api_key=llm_provider.api_key,
            base_url=llm_provider.api_base_url,
            model_name=llm_model,
            custom_params=llm_provider.custom_params or "{}"
        )
        
        subtitle_engine.correct_srt_file_with_llm(
            text, 
            output_subtitle_path,
            llm_engine=llm_engine,
            batch_size=batch_size
        )

#     生成字幕
#     def generate_subtitle(self, res_path):
#         subtitle_engine.generate_subtitle(res_path,res_path+".srt")
