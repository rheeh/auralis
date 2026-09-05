from __future__ import annotations
import base64
import logging
import os
import tempfile
from sqlalchemy import Sequence

from app.core.tts_engine import ConfigurableCloudTTSEngine, EdgeTTSEngine
from app.entity.tts_provider_entity import TTSProviderEntity
from app.models.po import TTSProviderPO
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.services.provider_backup_service import snapshot_provider_config


class TTSProviderService:

    def __init__(self, repository: TTSProviderRepository):
        """注入 repository"""
        self.repository = repository

    def create_tts_provider(self, entity: TTSProviderEntity):
        """创建 TTS 供应商。名称不可重复。"""
        existing = self.repository.get_by_name(entity.name)
        if existing:
            return None
        data = {k: v for k, v in entity.__dict__.items() if k not in {"created_at", "updated_at"}}
        data["provider_type"] = data.get("provider_type") or "cloud"
        data["api_base_url"] = data.get("api_base_url") or ""
        data["api_key"] = data.get("api_key") or ""
        data["model"] = data.get("model") or ""
        data["custom_params"] = data.get("custom_params") or "{}"
        data["status"] = 1 if data.get("status") is None else data.get("status")
        po = TTSProviderPO(**data)
        res = self.repository.create(po)
        snapshot_provider_config("tts", "after_create", res)
        result_data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        return TTSProviderEntity(**result_data)

    def get_all_tts_providers(self) -> list[TTSProviderEntity]:
        """查询所有tts供应商"""
        pos = self.repository.get_all()
        res = [TTSProviderEntity(**{k: v for k, v in po.__dict__.items() if not k.startswith("_")}) for po in pos]
        return res

    def get_tts_provider(self, tts_provider_id: int) -> TTSProviderEntity | None:
        """根据 ID 查询tts供应商"""
        po = self.repository.get_by_id(tts_provider_id)
        if not po:
            return None
        data = {k: v for k, v in po.__dict__.items() if not k.startswith("_")}
        res = TTSProviderEntity(**data)
        return res


    def update_tts_provider(self, tts_provider_id: int, data:dict) -> bool:
        """更新tts供应商
        - 可以只更新部分字段
        - 检查同名冲突
        - 检查project_id不能改变
        """
        po = self.repository.get_by_id(tts_provider_id)
        if po is None:
            return False
        name = data.get("name", po.name)
        existing = self.repository.get_by_name(name)
        if existing and existing.id != tts_provider_id:
            return False
        snapshot_provider_config("tts", "before_update", po)
        keep_when_empty = {"api_base_url", "api_key", "model", "custom_params"}
        data = {
            key: value
            for key, value in data.items()
            if not (key in keep_when_empty and value == "")
        }
        updated = self.repository.update(tts_provider_id, data)
        snapshot_provider_config("tts", "after_update", updated)
        return True

    def delete_tts_provider(self, tts_provider_id: int) -> bool:
        """删除tts供应商
        """
        po = self.repository.get_by_id(tts_provider_id)
        snapshot_provider_config("tts", "before_delete", po)
        res = self.repository.delete(tts_provider_id)
        return res

    def create_default_tts_provider(self):
        """创建默认的tts供应商"""
        existing = self.repository.get_by_id(1)
        if existing:
            if existing.name == "index_tts" and not existing.api_base_url:
                self.repository.update(existing.id, {
                    "name": "custom_cloud_tts",
                    "provider_type": "cloud",
                    "model": "",
                    "custom_params": "{}",
                })
            return
        if self.repository.get_by_name("custom_cloud_tts"):
            return
        po = TTSProviderPO(
            name="custom_cloud_tts",
            id=1,
            status=1,
            api_base_url="",
            api_key="",
            provider_type="cloud",
            model="",
            custom_params="{}",
        )
        self.repository.create(po)

    def test_tts_provider(self, entity: TTSProviderEntity):
        provider_type = (entity.provider_type or "cloud").lower()
        if provider_type == "edge":
            try:
                with tempfile.TemporaryDirectory(prefix="auralis_tts_test_") as tmp_dir:
                    save_path = os.path.join(tmp_dir, "edge_test.mp3")
                    audio_bytes = EdgeTTSEngine().synthesize("这是一段 Edge TTS 测试。", save_path=save_path)
                return True, "Edge-TTS 测试成功", {
                    "audio_data_url": _audio_data_url(audio_bytes, "audio/mpeg")
                }
            except Exception as exc:
                logging.exception("Edge-TTS provider test failed")
                return False, f"Edge-TTS 测试失败: {exc}", None

        api_base_url = entity.api_base_url
        if not api_base_url:
            return False, "TTS Base URL 不能为空", None
        if not entity.model:
            return False, "云端 TTS 模型不能为空", None

        try:
            with tempfile.TemporaryDirectory(prefix="auralis_tts_test_") as tmp_dir:
                save_path = os.path.join(tmp_dir, "cloud_test.wav")
                engine = ConfigurableCloudTTSEngine(
                    api_base_url,
                    api_key=entity.api_key,
                    model=entity.model,
                    custom_params=entity.custom_params or "{}",
                )
                instruction = None
                instruction_mode = "none"
                if engine._driver() == "dashscope_cosyvoice":
                    instruction_mode = engine._cosyvoice_instruction_mode()
                elif engine._instruction_field():
                    instruction_mode = "native"
                if instruction_mode in {"native", "structured"}:
                    instruction = "像面对面聊天，声音自然、克制，句尾轻轻收住。"
                audio_bytes = engine.synthesize(
                    "这是一段云端 TTS 测试。", save_path=save_path, instruction=instruction,
                )
            mode_label = {
                "native": "原生指令模式",
                "structured": "结构化指令模式",
                "mapped": "基础参数映射模式",
                "none": "基础生成模式",
            }.get(instruction_mode, instruction_mode)
            return True, f"云端 TTS 测试成功（{mode_label}）", {
                "audio_data_url": _audio_data_url(audio_bytes, "audio/wav")
            }
        except Exception as exc:
            logging.exception("TTS provider test failed: %s", exc)
            return False, f"TTS 测试失败: {exc}", None


def _audio_data_url(audio_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
