from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import getConfigPath
from app.models.po import AdaptationRunPO, ChapterPO, ChatSessionPO, EmotionPO, LinePO, ProjectPO, RolePO, StrengthPO
from app.services.knowledge_voice_design import KNOWLEDGE_ROLE_VOICES, enrich_dialogue_performance
from app.workflows.article.schemas import KnowledgeScript


class KnowledgeCommitService:
    def __init__(self, db: Session):
        self.db = db

    def commit_session(self, session_id: str, chapter_title: str | None = None, replace_chapter_lines: bool = True) -> dict[str, Any]:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None or session.source_type != "knowledge_article":
            raise ValueError("知识文章会话不存在")
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        if not run or not run.final_json:
            raise ValueError("知识音频脚本尚未确认，无法写入项目")
        if session.current_stage not in {"knowledge_script_ready", "completed"}:
            raise ValueError("当前阶段不能提交知识音频脚本")
        if run.committed_at and run.chapter_id:
            self._upgrade_existing_audio_design(session, run)
            return self._existing_summary(session, run)

        token = uuid4().hex
        now = datetime.now(timezone.utc)
        lease = self.db.execute(update(ChatSessionPO).where(
            ChatSessionPO.id == session_id,
            or_(ChatSessionPO.running_token.is_(None), ChatSessionPO.lease_expires_at < now),
        ).values(running_token=token, lease_expires_at=now + timedelta(minutes=10)))
        self.db.commit()
        if lease.rowcount != 1:
            raise ValueError("会话正在提交，请勿重复点击")
        self.db.expire(session)

        project = self.db.get(ProjectPO, session.project_id)
        if not project:
            raise ValueError("项目不存在")
        script = enrich_dialogue_performance(KnowledgeScript.model_validate(run.final_json).model_dump(mode="json"))
        try:
            session.current_stage = "committing"
            target_title = chapter_title or script["title"] or run.title
            chapter = self.db.get(ChapterPO, session.chapter_id) if session.chapter_id else None
            if chapter and chapter.project_id != session.project_id:
                raise ValueError("目标章节不属于当前项目")
            if not chapter:
                chapter = self.db.execute(select(ChapterPO).where(
                    ChapterPO.project_id == session.project_id, ChapterPO.title == target_title,
                )).scalar_one_or_none()
            if not chapter:
                chapter = ChapterPO(project_id=session.project_id, title=target_title)
                self.db.add(chapter)
                self.db.flush()
            chapter.title = target_title
            chapter.text_content = self._script_to_text(script)
            if replace_chapter_lines:
                self.db.execute(delete(LinePO).where(LinePO.chapter_id == chapter.id))

            roles = {role.name: role for role in self.db.execute(select(RolePO).where(RolePO.project_id == session.project_id)).scalars()}
            emotions = {item.name: item.id for item in self.db.execute(select(EmotionPO)).scalars()}
            strengths = {item.name: item.id for item in self.db.execute(select(StrengthPO)).scalars()}
            audio_dir = os.path.join(project.project_root_path or getConfigPath(), str(project.id), str(chapter.id), "audio")
            os.makedirs(audio_dir, exist_ok=True)
            created_roles = 0
            line_count = 0
            for segment in script["segments"]:
                for raw_line in segment["lines"]:
                    speaker = self._speaker(raw_line)
                    role = roles.get(speaker)
                    if not role:
                        role = RolePO(project_id=session.project_id, name=speaker)
                        self.db.add(role)
                        self.db.flush()
                        roles[speaker] = role
                        created_roles += 1
                    self._apply_role_voice(role, speaker)
                    line_count += 1
                    point_ids = list(dict.fromkeys((raw_line.get("knowledge_point_ids") or []) + (segment.get("knowledge_point_ids") or [])))
                    line = LinePO(
                        chapter_id=chapter.id, role_id=role.id, line_order=line_count,
                        text_content=str(raw_line.get("text") or raw_line.get("sound_prompt") or "").strip(),
                        line_type=raw_line.get("type", "dialogue"), track=raw_line.get("track", "voice"),
                        should_speak=1 if raw_line.get("should_speak", True) else 0,
                        scene_title=segment["title"], sound_prompt=raw_line.get("sound_prompt") or None,
                        voice_profile=raw_line.get("voice_profile") or None,
                        production_note=raw_line.get("production_note") or None,
                        knowledge_metadata={
                            "segment_id": segment["id"], "segment_title": segment["title"],
                            "segment_type": segment["segment_type"], "knowledge_point_ids": point_ids,
                            "content_origin": raw_line.get("content_origin", "fact_from_source"),
                        },
                        emotion_id=emotions.get(raw_line.get("emotion")) or emotions.get("平静"),
                        strength_id=strengths.get(raw_line.get("strength")) or strengths.get("中等"),
                    )
                    self.db.add(line)
                    self.db.flush()
                    line.audio_path = os.path.join(audio_dir, f"id_{line.id}.wav")

            now = datetime.now(timezone.utc)
            run.chapter_id = chapter.id
            run.draft_json = script
            run.final_json = script
            run.status = "committed"
            run.current_stage = "completed"
            run.committed_at = now
            session.chapter_id = chapter.id
            session.status = "completed"
            session.current_stage = "completed"
            session.completed_at = now
            session.active_confirm_type = None
            session.pending_confirm_json = None
            session.running_token = None
            session.lease_expires_at = None
            self.db.commit()
            return {"session_id": session.id, "project_id": session.project_id, "chapter_id": chapter.id, "created_roles": created_roles, "line_count": line_count, "already_committed": False, "source_type": "knowledge_article"}
        except Exception:
            self.db.rollback()
            locked = self.db.get(ChatSessionPO, session_id)
            if locked and locked.running_token == token:
                locked.running_token = None
                locked.lease_expires_at = None
                self.db.commit()
            raise

    def _upgrade_existing_audio_design(self, session: ChatSessionPO, run: AdaptationRunPO) -> None:
        script = enrich_dialogue_performance(KnowledgeScript.model_validate(run.final_json).model_dump(mode="json"))
        roles = {
            role.name: role
            for role in self.db.execute(select(RolePO).where(RolePO.project_id == session.project_id)).scalars()
        }
        for speaker, role in roles.items():
            self._apply_role_voice(role, speaker)

        emotions = {item.name: item.id for item in self.db.execute(select(EmotionPO)).scalars()}
        strengths = {item.name: item.id for item in self.db.execute(select(StrengthPO)).scalars()}
        lines = list(self.db.execute(
            select(LinePO).where(LinePO.chapter_id == run.chapter_id).order_by(LinePO.line_order.asc())
        ).scalars())
        raw_lines = [raw_line for segment in script["segments"] for raw_line in segment["lines"]]
        for line, raw_line in zip(lines, raw_lines):
            speaker = self._speaker(raw_line)
            role = roles.get(speaker)
            changed = False
            updates = {
                "role_id": role.id if role else line.role_id,
                "voice_profile": raw_line.get("voice_profile") or None,
                "production_note": raw_line.get("production_note") or None,
                "emotion_id": emotions.get(raw_line.get("emotion")) or emotions.get("平静"),
                "strength_id": strengths.get(raw_line.get("strength")) or strengths.get("中等"),
            }
            for field, value in updates.items():
                if getattr(line, field) != value:
                    setattr(line, field, value)
                    changed = True
            if changed and line.should_speak:
                line.status = "pending"
                line.is_done = 0
        run.draft_json = script
        run.final_json = script
        self.db.commit()

    @staticmethod
    def _apply_role_voice(role: RolePO, speaker: str) -> None:
        settings = KNOWLEDGE_ROLE_VOICES.get(speaker)
        if not settings:
            return
        role.edge_voice = settings["edge_voice"]
        role.tts_route = "edge"
        role.role_importance = "lead"
        # Knowledge-article audio is intentionally free-only. Clearing a stale
        # cloud voice binding prevents the runtime from selecting Aliyun/CosyVoice.
        role.default_voice_id = None

    def _existing_summary(self, session: ChatSessionPO, run: AdaptationRunPO) -> dict[str, Any]:
        count = self.db.scalar(select(func.count(LinePO.id)).where(LinePO.chapter_id == run.chapter_id))
        return {"session_id": session.id, "project_id": session.project_id, "chapter_id": run.chapter_id, "created_roles": 0, "line_count": count, "already_committed": True, "source_type": "knowledge_article"}

    @staticmethod
    def _speaker(line: dict[str, Any]) -> str:
        if line.get("type") == "sfx":
            return "音效"
        if line.get("type") == "bgm":
            return "BGM"
        return str(line.get("speaker") or "讲解者").strip() or "讲解者"

    @classmethod
    def _script_to_text(cls, script: dict[str, Any]) -> str:
        blocks = [f"《{script.get('title', '未命名知识音频')}》", f"表现形式：{script.get('adaptation_mode', '')}", ""]
        for segment in script.get("segments", []):
            blocks.append(f"[{segment.get('segment_type')}] {segment.get('title', '')}")
            for line in segment.get("lines", []):
                blocks.append(f"[{line.get('type')}｜{line.get('track')}｜{cls._speaker(line)}] {line.get('text', '')}")
            blocks.append("")
        return "\n".join(blocks)
