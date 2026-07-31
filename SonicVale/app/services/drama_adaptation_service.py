from __future__ import annotations
import json
import logging
import os
import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import getConfigPath
from app.core.llm_engine import LLMEngine
from app.core.prompts import get_audio_drama_adaptation_rules
from app.dto.drama_adaptation_dto import DramaAdaptationRequestDTO
from app.models.po import AdaptationRunPO, ChapterPO, LinePO, RolePO
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.emotion_repository import EmotionRepository
from app.repositories.line_repository import LineRepository
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.strength_repository import StrengthRepository
from app.services.timeline_service import TimelineService


class DramaAdaptationService:
    def __init__(self, db: Session):
        self.db = db
        self.project_repository = ProjectRepository(db)
        self.chapter_repository = ChapterRepository(db)
        self.line_repository = LineRepository(db)
        self.role_repository = RoleRepository(db)
        self.llm_provider_repository = LLMProviderRepository(db)
        self.emotion_repository = EmotionRepository(db)
        self.strength_repository = StrengthRepository(db)

    def adapt(self, dto: DramaAdaptationRequestDTO) -> dict[str, Any]:
        project = self.project_repository.get_by_id(dto.project_id)
        if not project:
            raise ValueError("项目不存在")
        if not project.llm_provider_id or not project.llm_model:
            raise ValueError("请先在项目中配置 LLM provider 和模型")

        run = AdaptationRunPO(
            project_id=dto.project_id,
            title=dto.title,
            source_text=dto.source_text,
            instruction=dto.instruction,
            scene_count=dto.scene_count,
            adaptation_density=dto.adaptation_density,
            status="running",
            current_stage="created",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            llm = self._make_llm(project)

            self._update_run(run, current_stage="parse_novel")
            parsed = self._call_json(llm, self._novel_parser_prompt(dto))
            self._update_run(run, parsed_json=parsed)

            self._update_run(run, current_stage="write_script")
            draft = self._call_json(llm, self._script_writer_prompt(dto, parsed))
            self._update_run(run, draft_json=draft)

            self._update_run(run, current_stage="polish_language")
            final_script = self._normalize_script(self._call_json(llm, self._language_prompt(parsed, draft)))
            self._update_run(run, final_json=final_script, status="script_ready", current_stage="script_ready")

            chapter_id = None
            if dto.commit_to_project:
                chapter = self.commit_run(run.id, dto.chapter_title, dto.replace_chapter_lines)
                chapter_id = chapter.id
                self.db.refresh(run)

            return {
                "run_id": run.id,
                "project_id": run.project_id,
                "chapter_id": chapter_id or run.chapter_id,
                "status": run.status,
                "current_stage": run.current_stage,
                "script": final_script,
                "message": "广播剧改编完成",
            }
        except Exception as exc:
            logging.exception("广播剧改编失败: %s", exc)
            self._update_run(run, status="failed", current_stage="failed", error_message=str(exc))
            raise

    def get_run(self, run_id: int) -> AdaptationRunPO | None:
        return self.db.get(AdaptationRunPO, run_id)

    def list_runs(self, project_id: int | None = None, limit: int = 50) -> list[AdaptationRunPO]:
        stmt = select(AdaptationRunPO).order_by(AdaptationRunPO.updated_at.desc()).limit(max(1, min(limit, 200)))
        if project_id:
            stmt = (
                select(AdaptationRunPO)
                .where(AdaptationRunPO.project_id == project_id)
                .order_by(AdaptationRunPO.updated_at.desc())
                .limit(max(1, min(limit, 200)))
            )
        return list(self.db.execute(stmt).scalars().all())

    def commit_run(self, run_id: int, chapter_title: str | None = None, replace_chapter_lines: bool = True) -> ChapterPO:
        run = self.get_run(run_id)
        if not run:
            raise ValueError("改编运行记录不存在")
        if run.session_id and run.is_conversational:
            from app.services.drama_commit_service import DramaCommitService
            result = DramaCommitService(self.db).commit_session(
                run.session_id, chapter_title=chapter_title, replace_chapter_lines=replace_chapter_lines
            )
            return self.db.get(ChapterPO, result["chapter_id"])
        if not run.final_json:
            raise ValueError("改编结果不存在，无法写入项目")

        project = self.project_repository.get_by_id(run.project_id)
        if not project:
            raise ValueError("项目不存在")

        script = self._normalize_script(run.final_json)
        target_title = chapter_title or script.get("title") or run.title
        chapter = self.chapter_repository.get_by_name(target_title, run.project_id)
        if chapter:
            self.chapter_repository.update(
                chapter.id,
                {
                    "title": target_title,
                    "project_id": run.project_id,
                    "text_content": self._script_to_text(script),
                },
            )
            self.db.refresh(chapter)
        else:
            chapter = self.chapter_repository.create(
                ChapterPO(project_id=run.project_id, title=target_title, text_content=self._script_to_text(script))
            )

        if replace_chapter_lines:
            TimelineService.clear_chapter_timeline(self.db, chapter.id)
            self.line_repository.delete_all_by_chapter_id(chapter.id)

        audio_path = os.path.join(project.project_root_path or getConfigPath(), str(run.project_id), str(chapter.id), "audio")
        os.makedirs(audio_path, exist_ok=True)

        emotions = {item.name: item.id for item in self.emotion_repository.get_all()}
        strengths = {item.name: item.id for item in self.strength_repository.get_all()}

        order = 1
        for scene in script.get("scenes", []):
            scene_title = scene.get("title") or "未命名场景"
            for line in scene.get("lines", []):
                speaker = self._speaker_name(line)
                role = self._ensure_role(run.project_id, speaker)
                po = LinePO(
                    chapter_id=chapter.id,
                    role_id=role.id,
                    line_order=order,
                    text_content=str(line.get("text") or "").strip(),
                    emotion_id=emotions.get(str(line.get("emotion") or "").strip()) or emotions.get("平静"),
                    strength_id=strengths.get(str(line.get("strength") or "").strip()) or strengths.get("中等"),
                    line_type=self._line_type(line),
                    track=self._track(line),
                    should_speak=1 if bool(line.get("shouldSpeak", line.get("should_speak", True))) else 0,
                    scene_title=scene_title,
                    sound_prompt=str(line.get("soundPrompt") or line.get("sound_prompt") or "").strip() or None,
                    voice_profile=str(line.get("voiceProfile") or line.get("voice_profile") or "").strip() or None,
                    production_note=str(line.get("productionNote") or line.get("production_note") or "").strip() or None,
                    audio_events=line.get("audioEvents") or line.get("audio_events") or None,
                )
                created = self.line_repository.create(po)
                self.line_repository.update(created.id, {"audio_path": os.path.join(audio_path, f"id_{created.id}.wav")})
                order += 1

        self._update_run(run, chapter_id=chapter.id, status="committed", current_stage="committed")
        return chapter

    def _make_llm(self, project) -> LLMEngine:
        provider = self.llm_provider_repository.get_by_id(project.llm_provider_id)
        if not provider:
            raise ValueError("LLM provider 不存在")
        return LLMEngine(provider.api_key, provider.api_base_url, project.llm_model, provider.custom_params)

    def _call_json(self, llm: LLMEngine, prompt: str) -> dict[str, Any]:
        content = llm.generate_text(prompt)
        return self._parse_json(content)

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
        if fenced:
            text = fenced.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError("LLM 没有返回可解析 JSON")

    def _update_run(self, run: AdaptationRunPO, **fields):
        for key, value in fields.items():
            setattr(run, key, value)
        self.db.commit()
        self.db.refresh(run)

    def _normalize_script(self, raw: dict[str, Any]) -> dict[str, Any]:
        script = raw.get("script") if isinstance(raw.get("script"), dict) else raw
        script.setdefault("title", "未命名广播剧")
        script.setdefault("logline", "")
        script.setdefault("characters", [])
        script.setdefault("scenes", [])
        for scene_index, scene in enumerate(script["scenes"], start=1):
            scene.setdefault("title", f"第 {scene_index} 场")
            scene.setdefault("location", "")
            scene.setdefault("mood", "")
            scene.setdefault("lines", [])
            for line in scene["lines"]:
                line["type"] = self._line_type(line)
                line["track"] = self._track(line)
                line["shouldSpeak"] = line["type"] in {"dialogue", "narration"} and bool(
                    line.get("shouldSpeak", line.get("should_speak", True))
                )
                line.setdefault("speaker", "旁白" if line["type"] == "narration" else "音效")
                line.setdefault("text", "")
        return script

    def _line_type(self, line: dict[str, Any]) -> str:
        value = str(line.get("type") or line.get("line_type") or "dialogue").lower()
        return value if value in {"dialogue", "narration", "sfx", "bgm"} else "dialogue"

    def _track(self, line: dict[str, Any]) -> str:
        value = str(line.get("track") or "").lower()
        if value in {"voice", "narration", "sfx", "bgm"}:
            return value
        return {"dialogue": "voice", "narration": "narration", "sfx": "sfx", "bgm": "bgm"}[self._line_type(line)]

    def _speaker_name(self, line: dict[str, Any]) -> str:
        line_type = self._line_type(line)
        if line_type == "narration":
            return "旁白"
        if line_type == "sfx":
            return "音效"
        if line_type == "bgm":
            return "BGM"
        return str(line.get("speaker") or "未知角色").strip() or "未知角色"

    def _ensure_role(self, project_id: int, name: str) -> RolePO:
        role = self.role_repository.get_by_name(name, project_id)
        if role:
            return role
        return self.role_repository.create(RolePO(project_id=project_id, name=name))

    def _novel_parser_prompt(self, dto: DramaAdaptationRequestDTO) -> str:
        return "\n\n".join(
            [
                "你是解析小说 Agent。只输出严格 JSON，不要解释。",
                f"目标场次数：{dto.scene_count}",
                get_audio_drama_adaptation_rules(),
                "逐句分类并制定 audioStrategy，再抽取剧情、人物、场景、冲突、声音线索和音效/BGM；不要默认保留叙述。",
                "JSON schema:",
                json.dumps(
                    {
                        "title": "作品名",
                        "logline": "一句话剧情",
                        "genre": "类型",
                        "narratorPointOfView": "旁白视角",
                        "characters": [
                            {
                                "name": "角色名",
                                "role": "角色功能",
                                "traits": ["性格"],
                                "motivation": "动机",
                                "voiceClues": "声线线索",
                            }
                        ],
                        "scenePlan": [
                            {
                                "title": "场景名",
                                "location": "地点",
                                "mood": "情绪",
                                "plotBeats": ["剧情节拍"],
                                "likelySfx": ["音效"],
                                "likelyBgm": "音乐方向",
                            }
                        ],
                        "contentMap": [
                            {
                                "source": "原文句子或信息点",
                                "category": "对话|动作|环境|心理|背景信息|转场|视觉描写",
                                "audioStrategy": "dialogue|sfx|bgm|silence|narration|delete",
                                "keepAsNarration": False,
                                "reason": "声音化或删除理由",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                "小说正文:",
                dto.source_text[:50000],
            ]
        )

    def _script_writer_prompt(self, dto: DramaAdaptationRequestDTO, parsed: dict[str, Any]) -> str:
        return "\n\n".join(
            [
                "你是生成广播剧台本 Agent。只输出严格 JSON。",
                get_audio_drama_adaptation_rules(),
                f"改编密度：{dto.adaptation_density}",
                f"用户指令：{dto.instruction or '生成可直接制作的广播剧台本。'}",
                "规则：dialogue 只能是人物说出口的话；narration 只能是旁白；sfx/bgm 只能是声音提示，不写成可朗读句。",
                "严格执行 contentMap；禁止把 delete/sfx/bgm 内容重新写成长旁白。禁止连续旁白，单条旁白通常不超过45个汉字，旁白字数目标不超过人物可朗读文本的15%。",
                "每一行必须包含 type、track、shouldSpeak、speaker、text、emotion、strength、voiceProfile、soundPrompt、productionNote。",
                "JSON schema:",
                json.dumps(self._script_schema(), ensure_ascii=False),
                "小说解析 JSON:",
                json.dumps(parsed, ensure_ascii=False),
                "小说正文:",
                dto.source_text[:50000],
            ]
        )

    def _language_prompt(self, parsed: dict[str, Any], draft: dict[str, Any]) -> str:
        return "\n\n".join(
            [
                "你是生成广播剧语言 Agent。只输出严格 JSON。",
                "把台本整理成最终可编辑、可进入语音 API 的广播剧工程。",
                get_audio_drama_adaptation_rules(),
                "这是最后一次声音审计：删除被对白、音效或音乐重复表达的旁白；拆散连续旁白；不要为了文采重新补回视觉描写。",
                "硬规则：dialogue/narration shouldSpeak=true；sfx/bgm shouldSpeak=false。",
                "sfx/bgm 的 text 是音频素材或生成提示，绝不能作为台词朗读。",
                "不得模仿名人或真实人物声音；voiceProfile 只能写年龄、音色、节奏、情绪等通用描述。",
                "JSON schema:",
                json.dumps(self._script_schema(), ensure_ascii=False),
                "小说解析 JSON:",
                json.dumps(parsed, ensure_ascii=False),
                "广播剧台本 JSON:",
                json.dumps(draft, ensure_ascii=False),
            ]
        )

    def _script_schema(self) -> dict[str, Any]:
        return {
            "title": "作品名",
            "logline": "一句话看点",
            "characters": [{"name": "角色名", "role": "角色功能", "voiceProfile": "TTS 声线建议"}],
            "scenes": [
                {
                    "title": "场景名",
                    "location": "地点",
                    "mood": "情绪",
                    "lines": [
                        {
                            "type": "dialogue|narration|sfx|bgm",
                            "track": "voice|narration|sfx|bgm",
                            "shouldSpeak": True,
                            "speaker": "角色名/旁白/音效/BGM",
                            "text": "台词、旁白、音效提示或 BGM 提示",
                            "emotion": "高兴/生气/伤心/害怕/厌恶/低落/惊喜/平静/嘲讽/悲愤",
                            "strength": "微弱/稍弱/中等/较强/强烈",
                            "voiceProfile": "声线建议",
                            "soundPrompt": "音效或 BGM 提示",
                            "productionNote": "制作备注",
                        }
                    ],
                }
            ],
        }

    def _script_to_text(self, script: dict[str, Any]) -> str:
        blocks = [f"《{script.get('title', '未命名广播剧')}》", script.get("logline", ""), ""]
        for index, scene in enumerate(script.get("scenes", []), start=1):
            blocks.append(f"第 {index} 场｜{scene.get('title', '')}｜{scene.get('location', '')}｜{scene.get('mood', '')}")
            for line in scene.get("lines", []):
                blocks.append(
                    f"[{self._line_type(line)}｜{self._track(line)}｜{self._speaker_name(line)}｜"
                    f"{line.get('emotion', '')}｜shouldSpeak={bool(line.get('shouldSpeak', True))}] {line.get('text', '')}"
                )
            blocks.append("")
        return "\n".join(blocks)
