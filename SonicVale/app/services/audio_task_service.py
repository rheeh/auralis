from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.po import AudioTaskPO, ChatSessionPO, LinePO


class AudioTaskService:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        queue,
        project_id: int,
        chapter_id: int,
        line: LinePO,
        dto,
        session_id: str | None = None,
        task: AudioTaskPO | None = None,
    ) -> AudioTaskPO:
        self._validate_context(project_id, chapter_id, line, session_id)
        if queue.full():
            raise OverflowError("队列已满，请稍后重试")

        if task:
            task.status = "queued"
            task.attempt = (task.attempt or 0) + 1
            task.error_code = None
            task.error_message = None
            task.started_at = None
            task.completed_at = None
            task.review_status = "pending"
            task.review_note = None
        else:
            task = AudioTaskPO(
                id=f"tts_{uuid4().hex}", project_id=project_id, chapter_id=chapter_id,
                session_id=session_id, line_id=line.id, status="queued", audio_path=line.audio_path,
            )
            self.db.add(task)
        line.status = "processing"
        line.is_done = 0
        self.db.commit()
        queue.put_nowait({
            "task_id": task.id,
            "project_id": project_id,
            "chapter_id": chapter_id,
            "session_id": session_id,
            "dto": dto,
        })
        return task

    def create_skipped(
        self, project_id: int, chapter_id: int, line: LinePO, session_id: str | None = None,
    ) -> AudioTaskPO:
        self._validate_context(project_id, chapter_id, line, session_id)
        task = AudioTaskPO(
            id=f"tts_{uuid4().hex}", project_id=project_id, chapter_id=chapter_id,
            session_id=session_id, line_id=line.id, status="skipped",
            audio_path=line.audio_path, completed_at=datetime.now(timezone.utc),
        )
        line.status = "pending"
        line.is_done = 1
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def mark(self, task_id: str, status: str, error: Exception | None = None, audio_path: str | None = None) -> AudioTaskPO | None:
        task = self.db.get(AudioTaskPO, task_id)
        if not task:
            return None
        now = datetime.now(timezone.utc)
        task.status = status
        if status == "processing":
            task.started_at = now
        if status in {"done", "failed", "skipped", "cancelled"}:
            task.completed_at = now
        if error:
            task.error_code = "TTS_GENERATION_FAILED"
            task.error_message = str(error)[:1000]
        else:
            task.error_code = None
            task.error_message = None
        if audio_path:
            task.audio_path = audio_path
        self.db.commit()
        self.db.refresh(task)
        return task

    def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        rows = self.db.execute(
            select(AudioTaskPO, LinePO)
            .join(LinePO, LinePO.id == AudioTaskPO.line_id)
            .where(AudioTaskPO.session_id == session_id)
            .order_by(AudioTaskPO.created_at.asc())
        ).all()
        return [self.serialize(task, line) for task, line in rows]

    def summary(self, session_id: str) -> dict[str, Any]:
        tasks = self.list_for_session(session_id)
        counts = {key: 0 for key in ["queued", "processing", "done", "failed", "skipped", "cancelled"]}
        for task in tasks:
            counts[task["status"]] = counts.get(task["status"], 0) + 1
        total = len(tasks)
        completed = counts["done"] + counts["skipped"]
        return {
            "session_id": session_id,
            "counts": counts,
            "total": total,
            "completed": completed,
            "progress": round(completed / total * 100) if total else 0,
            "tasks": tasks,
        }

    def latest_for_line(self, session_id: str, line_id: int) -> AudioTaskPO | None:
        return self.db.execute(
            select(AudioTaskPO).where(
                AudioTaskPO.session_id == session_id,
                AudioTaskPO.line_id == line_id,
            ).order_by(AudioTaskPO.created_at.desc()).limit(1)
        ).scalar_one_or_none()

    def get_for_session(self, session_id: str, task_id: str) -> AudioTaskPO:
        task = self.db.get(AudioTaskPO, task_id)
        if not task or task.session_id != session_id:
            raise ValueError("音频任务不存在")
        return task

    def review(self, session_id: str, task_id: str, approved: bool, note: str = "") -> AudioTaskPO:
        task = self.get_for_session(session_id, task_id)
        if task.status != "done":
            raise ValueError("只有生成完成的音频可以审核")
        task.review_status = "approved" if approved else "rejected"
        task.review_note = note.strip() or None
        self.db.commit()
        self.db.refresh(task)
        return task

    @staticmethod
    def serialize(task: AudioTaskPO, line: LinePO | None = None) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "project_id": task.project_id,
            "chapter_id": task.chapter_id,
            "session_id": task.session_id,
            "line_id": task.line_id,
            "line_order": line.line_order if line else None,
            "speaker_role_id": line.role_id if line else None,
            "text": line.text_content if line else None,
            "track": line.track if line else None,
            "status": task.status,
            "attempt": task.attempt,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "audio_path": task.audio_path,
            "review_status": task.review_status,
            "review_note": task.review_note,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
        }

    def _validate_context(self, project_id: int, chapter_id: int, line: LinePO, session_id: str | None) -> None:
        if line.chapter_id != chapter_id:
            raise ValueError("台词不属于目标章节")
        if session_id:
            session = self.db.get(ChatSessionPO, session_id)
            if not session or session.project_id != project_id or session.chapter_id != chapter_id:
                raise ValueError("会话、项目与章节不匹配")
