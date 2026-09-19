from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.po import AudioTaskPO, ChatSessionPO, LinePO


class ActiveAudioTaskError(ValueError):
    def __init__(self, task):
        super().__init__('本句已有活动配音任务；新指导未保存，请等待任务结束后再提交')
        self.task = task


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
        if getattr(queue,'_auralis_loop',None):
            from app.runtime.queue import ThreadsafeQueueProxy
            queue=ThreadsafeQueueProxy(queue,queue._auralis_loop)
        if queue.full():
            raise OverflowError("队列已满，请稍后重试")

        from app.services.speech.request import prepare_request, output_path
        # Serialize enqueue and regenerate before reading active attempts. This
        # SQLite write lock also protects guidance + input snapshot as one unit.
        self.db.execute(update(LinePO).where(LinePO.id == line.id).values(id=line.id))
        self.db.refresh(line)
        active = self.db.scalar(select(AudioTaskPO).where(AudioTaskPO.line_id==line.id,
            AudioTaskPO.status.in_(['queued','processing','completing'])).limit(1))
        if active:
            self.db.commit()
            return active
        request, snapshot, fingerprint = prepare_request(self.db, project_id, line.id)
        token = uuid4().hex
        request['output_path'] = output_path(self.db,project_id,chapter_id,line.id,token)
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
        task.run_token=token
        task.input_snapshot=snapshot
        task.input_fingerprint=fingerprint
        task.audio_path=request['output_path']
        line.status = "processing"
        line.is_done = 0
        from sqlalchemy.exc import IntegrityError
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing=self.db.scalar(select(AudioTaskPO).where(AudioTaskPO.line_id==line.id,
                AudioTaskPO.status.in_(['queued','processing','completing'])).limit(1))
            if existing:return existing
            raise
        try:
            queue.put_nowait({"task_id":task.id,"project_id":project_id,"chapter_id":chapter_id,
                "session_id":session_id,"run_token":token,"request":request})
        except Exception:
            task.status='failed';task.error_code='ENQUEUE_FAILED'
            task.error_message='入队失败，请显式重试';line.status='pending'
            self.db.commit()
            raise
        return task

    def regenerate(self, queue, session_id: str, line_id: int, prompt: str):
        """Save guidance and queue its snapshot, or reject without changing it."""
        try:
            self.db.execute(update(LinePO).where(LinePO.id == line_id).values(id=line_id))
            self.db.expire_all()
            session = self.db.get(ChatSessionPO, session_id)
            line = self.db.get(LinePO, line_id)
            if not session or session.deleted_at or not line:
                raise ValueError('会话或台词不存在')
            self._validate_context(session.project_id, session.chapter_id, line, session_id)
            if session.current_stage != 'completed' or not line.should_speak or line.track in {'sfx', 'bgm'}:
                raise ValueError('当前台词不能生成角色配音')
            active = self.db.scalar(select(AudioTaskPO).where(AudioTaskPO.line_id == line_id,
                AudioTaskPO.status.in_(['queued', 'processing', 'completing'])))
            if active:
                raise ActiveAudioTaskError(active)
            from app.repositories.line_repository import LineRepository
            from app.services.production.line_commands import LineCommands
            LineCommands(LineRepository(self.db)).update(line_id, {'production_note': prompt.strip() or None}, commit=False)
            self.db.flush()
            return self.enqueue(queue, session.project_id, session.chapter_id, line, None, session_id)
        except Exception:
            self.db.rollback()
            raise

    def claim(self, task_id, token):
        result=self.db.execute(update(AudioTaskPO).where(AudioTaskPO.id==task_id,
            AudioTaskPO.run_token==token,AudioTaskPO.status=='queued').values(status='processing',started_at=datetime.now(timezone.utc)))
        self.db.commit()
        return result.rowcount==1

    def complete(self, task_id, token, path):
        from app.services.speech.request import prepare_request
        from app.services.timeline_service import TimelineService
        import soundfile as sf
        info=sf.info(path)
        if info.frames<=0:
            raise ValueError('配音结果不是有效音频')
        self.db.expire_all()
        task=self.db.get(AudioTaskPO,task_id)
        if not task or task.run_token!=token or task.status!='processing':
            return False
        if path != task.audio_path:
            raise ValueError('结果路径不属于当前 attempt')
        # Claim the completion before reading current dependencies. SQLite's write
        # transaction prevents an edit from interleaving with adoption.
        claimed=self.db.execute(update(AudioTaskPO).where(AudioTaskPO.id==task_id,
            AudioTaskPO.run_token==token,AudioTaskPO.status=='processing').values(status='completing'))
        if claimed.rowcount!=1:
            self.db.rollback();return False
        try:
            line=self.db.get(LinePO,task.line_id)
            try:
                _,_,current=prepare_request(self.db,task.project_id,task.line_id)
            except ValueError:
                current=None
            current_input=current==task.input_fingerprint
            version={'id':token,'label':f'版本 {len(line.audio_versions or [])+1}', 'kind':'generated',
                'audio_path':path,'task_id':task.id,'input_fingerprint':task.input_fingerprint,
                'input_snapshot':task.input_snapshot,'text':(task.input_snapshot or {}).get('prepared',{}).get('original_text'),
                'created_at':datetime.now(timezone.utc).isoformat(), 'stale':not current_input}
            line.audio_versions=[*(line.audio_versions or []),version]
            if current_input:
                line.active_audio_version_id=token;line.active_audio_variant_id=None
                line.audio_path=path;line.status='done';line.is_done=1
                TimelineService.invalidate_line(self.db,line.id,commit=False)
            else:
                line.status='pending';line.is_done=0
            task.status='done' if current_input else 'stale'
            task.completed_at=datetime.now(timezone.utc)
            self.db.commit()
            return current_input
        except Exception:
            self.db.rollback();raise

    def fail(self, task_id, token, message, code='TTS_GENERATION_FAILED'):
        self.db.rollback()
        task=self.db.get(AudioTaskPO,task_id)
        if not task or task.run_token!=token or task.status not in {'queued','processing'}:
            return
        from app.services.tts_trace_service import redact
        task.status='failed';task.error_code=code;task.error_message=redact(message)
        task.completed_at=datetime.now(timezone.utc)
        line=self.db.get(LinePO,task.line_id)
        if line and line.status=='processing':
            line.status='failed';line.is_done=0
        self.db.commit()

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
        attempts = self.list_for_session(session_id)
        latest = {task['line_id']:task for task in attempts}
        tasks = list(latest.values())
        counts = {key: 0 for key in ["queued", "processing", "done", "failed", "skipped", "cancelled"]}
        for task in tasks:
            counts[task["status"]] = counts.get(task["status"], 0) + 1
        execution_total=len(tasks)
        execution_completed=counts["done"]+counts["skipped"]
        session=self.db.get(ChatSessionPO,session_id)
        lines=list(self.db.scalars(select(LinePO).where(LinePO.chapter_id==session.chapter_id,
            LinePO.should_speak!=0,LinePO.track.notin_(['sfx','bgm'])))) if session.chapter_id else []
        from app.services.production.audio_state import generation_state
        total=len(lines)
        completed=sum(not generation_state(self.db,line)['needs_generation'] for line in lines)
        return {
            "session_id": session_id,
            "counts": counts,
            "total": total,
            "completed": completed,
            "progress": round(completed / total * 100) if total else 0,
            "tasks": tasks,
            "attempt_count":sum(item["attempt"] for item in attempts),
            "execution_progress": round(execution_completed / execution_total * 100) if execution_total else 0,
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
            "input_fingerprint": task.input_fingerprint,
            "input_snapshot": task.input_snapshot,
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
        from app.models.po import ChapterPO
        chapter=self.db.get(ChapterPO,chapter_id)
        if not chapter or chapter.project_id!=project_id:
            raise ValueError("章节不属于目标项目")
        if line.chapter_id != chapter_id:
            raise ValueError("台词不属于目标章节")
        if session_id:
            session = self.db.get(ChatSessionPO, session_id)
            if not session or session.project_id != project_id or session.chapter_id != chapter_id:
                raise ValueError("会话、项目与章节不匹配")
