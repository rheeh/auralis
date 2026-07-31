from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import getConfigPath
from app.models.po import AdaptationDraftRevisionPO, AdaptationRunPO, ChapterPO, ChatSessionPO, EmotionPO, LinePO, ProjectPO, RolePO, StrengthPO
from app.workflows.drama.schemas import DramaScript
from app.services.timeline_service import TimelineService


class DramaCommitService:
    def __init__(self, db: Session):
        self.db = db

    def commit_session(
        self,
        session_id: str,
        chapter_title: str | None = None,
        replace_chapter_lines: bool = True,
    ) -> dict[str, Any]:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        if not run or not run.final_json:
            raise ValueError("剧本尚未确认，无法写入项目")
        if session.current_stage not in {"script_draft_ready", "completed"}:
            raise ValueError("当前阶段不能提交剧本")

        if run.committed_at and run.chapter_id:
            return self._existing_summary(session, run)

        lease_token = uuid4().hex
        now = datetime.now(timezone.utc)
        lease = self.db.execute(
            update(ChatSessionPO)
            .where(
                ChatSessionPO.id == session_id,
                or_(ChatSessionPO.running_token.is_(None), ChatSessionPO.lease_expires_at < now),
            )
            .values(running_token=lease_token, lease_expires_at=now + timedelta(minutes=10))
        )
        self.db.commit()
        if lease.rowcount != 1:
            raise ValueError("会话正在提交，请勿重复点击")
        self.db.expire(session)

        project = self.db.get(ProjectPO, session.project_id)
        if not project:
            raise ValueError("项目不存在")
        script = DramaScript.model_validate(run.final_json).model_dump()

        try:
            session.current_stage = "committing"
            target_title = chapter_title or script.get("title") or run.title
            chapter = self.db.get(ChapterPO, session.chapter_id) if session.chapter_id else None
            if chapter and chapter.project_id != session.project_id:
                raise ValueError("目标章节不属于当前项目")
            if not chapter:
                chapter = self.db.execute(
                    select(ChapterPO).where(ChapterPO.project_id == session.project_id, ChapterPO.title == target_title)
                ).scalar_one_or_none()
            if not chapter:
                chapter = ChapterPO(project_id=session.project_id, title=target_title)
                self.db.add(chapter)
                self.db.flush()

            chapter.title = target_title
            chapter.text_content = self._script_to_text(script)
            if replace_chapter_lines:
                TimelineService.clear_chapter_timeline(self.db, chapter.id)
                self.db.execute(delete(LinePO).where(LinePO.chapter_id == chapter.id))

            roles = {
                role.name: role
                for role in self.db.execute(select(RolePO).where(RolePO.project_id == session.project_id)).scalars()
            }
            role_revision = self.db.execute(
                select(AdaptationDraftRevisionPO)
                .where(
                    AdaptationDraftRevisionPO.session_id == session.id,
                    AdaptationDraftRevisionPO.draft_type == "roles",
                )
                .order_by(AdaptationDraftRevisionPO.revision.desc())
                .limit(1)
            ).scalar_one_or_none()
            confirmed_role_settings = {
                str(item.get("name") or "").strip(): item
                for item in ((role_revision.payload_json or {}).get("roles", []) if role_revision else [])
                if item.get("selected", True)
            }
            emotions = {item.name: item.id for item in self.db.execute(select(EmotionPO)).scalars()}
            strengths = {item.name: item.id for item in self.db.execute(select(StrengthPO)).scalars()}
            audio_dir = os.path.join(project.project_root_path or getConfigPath(), str(project.id), str(chapter.id), "audio")
            os.makedirs(audio_dir, exist_ok=True)

            line_count = 0
            created_role_count = 0
            for scene in script.get("scenes", []):
                for raw_line in scene.get("lines", []):
                    speaker = self._speaker_name(raw_line)
                    role = roles.get(speaker)
                    if not role:
                        settings = confirmed_role_settings.get(speaker, {})
                        role = RolePO(
                            project_id=session.project_id,
                            name=speaker,
                            default_voice_id=settings.get("default_voice_id"),
                            avatar_path=settings.get("avatar_path"),
                        )
                        self.db.add(role)
                        self.db.flush()
                        roles[speaker] = role
                        created_role_count += 1
                    else:
                        settings = confirmed_role_settings.get(speaker, {})
                        if settings.get("default_voice_id"):
                            role.default_voice_id = settings["default_voice_id"]
                        if settings.get("avatar_path"):
                            role.avatar_path = settings["avatar_path"]
                    line_count += 1
                    line = LinePO(
                        chapter_id=chapter.id,
                        role_id=role.id,
                        line_order=line_count,
                        text_content=str(raw_line.get("text") or "").strip(),
                        line_type=raw_line.get("type", "dialogue"),
                        track=raw_line.get("track", "voice"),
                        should_speak=1 if raw_line.get("shouldSpeak", True) else 0,
                        scene_title=scene.get("title") or "未命名场景",
                        sound_prompt=raw_line.get("soundPrompt") or None,
                        voice_profile=raw_line.get("voiceProfile") or None,
                        production_note=raw_line.get("productionNote") or None,
                        audio_events=raw_line.get("audioEvents") or raw_line.get("audio_events") or None,
                        emotion_id=emotions.get(raw_line.get("emotion")) or emotions.get("平静"),
                        strength_id=strengths.get(raw_line.get("strength")) or strengths.get("中等"),
                    )
                    self.db.add(line)
                    self.db.flush()
                    line.audio_path = os.path.join(audio_dir, f"id_{line.id}.wav")

            now = datetime.now(timezone.utc)
            run.chapter_id = chapter.id
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
            return {
                "session_id": session.id,
                "project_id": session.project_id,
                "chapter_id": chapter.id,
                "created_roles": created_role_count,
                "line_count": line_count,
                "already_committed": False,
            }
        except Exception:
            self.db.rollback()
            locked_session = self.db.get(ChatSessionPO, session_id)
            if locked_session and locked_session.running_token == lease_token:
                locked_session.running_token = None
                locked_session.lease_expires_at = None
                self.db.commit()
            raise

    def _existing_summary(self, session: ChatSessionPO, run: AdaptationRunPO) -> dict[str, Any]:
        line_count = self.db.execute(
            select(func.count(LinePO.id)).where(LinePO.chapter_id == run.chapter_id)
        ).scalar_one()
        return {
            "session_id": session.id,
            "project_id": session.project_id,
            "chapter_id": run.chapter_id,
            "created_roles": 0,
            "line_count": line_count,
            "already_committed": True,
        }

    @staticmethod
    def _speaker_name(line: dict[str, Any]) -> str:
        if line.get("type") == "narration":
            return "旁白"
        if line.get("type") == "sfx":
            return "音效"
        if line.get("type") == "bgm":
            return "BGM"
        return str(line.get("speaker") or "未知角色").strip() or "未知角色"

    def _script_to_text(self, script: dict[str, Any]) -> str:
        blocks = [f"《{script.get('title', '未命名广播剧')}》", script.get("logline", ""), ""]
        for index, scene in enumerate(script.get("scenes", []), start=1):
            blocks.append(f"第 {index} 场｜{scene.get('title', '')}｜{scene.get('location', '')}｜{scene.get('mood', '')}")
            for line in scene.get("lines", []):
                blocks.append(f"[{line.get('type')}｜{line.get('track')}｜{self._speaker_name(line)}] {line.get('text', '')}")
            blocks.append("")
        return "\n".join(blocks)
