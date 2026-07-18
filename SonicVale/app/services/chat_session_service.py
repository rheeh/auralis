from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DRAMA_WORKFLOW_MAX_SOURCE_CHARS, KNOWLEDGE_ARTICLE_ENABLED, WORKFLOW_CHAT_UI_ENABLED
from app.dto.chat_dto import ChatSessionCreateDTO, SourceDocumentCreateDTO
from app.models.po import (
    AdaptationRunPO,
    ArticleSourcePO,
    ChatMessagePO,
    ChatSessionPO,
    ProjectPO,
    SourceDocumentPO,
    WorkflowEventPO,
)
from app.services.content_adaptation_service import ContentAdaptationService


class ChatSessionService:
    def __init__(self, db: Session):
        self.db = db

    def create_source_document(self, dto: SourceDocumentCreateDTO) -> SourceDocumentPO:
        if not self.db.get(ProjectPO, dto.project_id):
            raise ValueError("项目不存在")
        if len(dto.content) > DRAMA_WORKFLOW_MAX_SOURCE_CHARS:
            raise ValueError(f"原文不能超过 {DRAMA_WORKFLOW_MAX_SOURCE_CHARS} 字")
        document = SourceDocumentPO(project_id=dto.project_id, name=dto.name, content=dto.content)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def create(self, dto: ChatSessionCreateDTO) -> dict[str, Any]:
        if not WORKFLOW_CHAT_UI_ENABLED:
            raise ValueError("对话式改编功能当前未启用")
        if dto.source_type == "knowledge_article" and not KNOWLEDGE_ARTICLE_ENABLED:
            raise ValueError("知识文章音频功能当前未启用")
        project = self.db.get(ProjectPO, dto.project_id)
        if not project:
            raise ValueError("项目不存在")
        if dto.chapter_id:
            from app.models.po import ChapterPO
            chapter = self.db.get(ChapterPO, dto.chapter_id)
            if not chapter or chapter.project_id != dto.project_id:
                raise ValueError("目标章节不存在或不属于当前项目")

        source_text = dto.source_text.strip() if dto.source_text else None
        if dto.source_document_id:
            document = self.db.get(SourceDocumentPO, dto.source_document_id)
            if not document or document.project_id != dto.project_id:
                raise ValueError("原文文档不存在或不属于当前项目")
            source_text = document.content
        article_source = None
        if dto.article_source_id:
            article_source = self.db.get(ArticleSourcePO, dto.article_source_id)
            if not article_source or article_source.project_id != dto.project_id:
                raise ValueError("文章来源不存在或不属于当前项目")
            source_text = article_source.normalized_content
        if not source_text:
            raise ValueError("原文正文不能为空")
        if len(source_text) > DRAMA_WORKFLOW_MAX_SOURCE_CHARS:
            raise ValueError(f"原文正文不能超过 {DRAMA_WORKFLOW_MAX_SOURCE_CHARS} 字")

        session_id = f"sess_{uuid4().hex}"
        title = dto.title or source_text.splitlines()[0][:80] or "新改编会话"
        run = AdaptationRunPO(
            project_id=dto.project_id,
            chapter_id=dto.chapter_id,
            title=title,
            source_kind=dto.source_type,
            source_text=None,
            instruction=dto.instruction,
            status="running",
            current_stage="created",
            session_id=session_id,
            is_conversational=True,
        )
        session = ChatSessionPO(
            id=session_id,
            project_id=dto.project_id,
            chapter_id=dto.chapter_id,
            title=title,
            source_type=dto.source_type,
            adaptation_mode=dto.adaptation_mode,
            article_category=dto.article_category,
            learning_goal=dto.learning_goal,
            target_duration_minutes=dto.target_duration_minutes,
            verification_mode=dto.verification_mode,
            source_text=source_text,
            source_document_id=dto.source_document_id,
            article_source_id=dto.article_source_id,
            instruction=dto.instruction,
        )
        self.db.add_all([run, session])
        self.db.flush()
        session.adaptation_run_id = run.id
        if article_source:
            article_source.session_id = session_id
        self.db.add(ChatMessagePO(
            id=f"msg_{uuid4().hex}",
            session_id=session_id,
            role="user" if dto.instruction and dto.instruction.strip() else "assistant",
            message_type="instruction" if dto.instruction and dto.instruction.strip() else "status",
            content=(dto.instruction or (
                "已收到文章正文，准备建立知识音频会话。"
                if dto.source_type == "knowledge_article"
                else "已收到小说原文，准备开始解析。"
            )).strip(),
            payload_json={
                "source_chars": len(source_text),
                "source": "session_creation",
                "source_type": dto.source_type,
            },
        ))
        self.db.commit()
        self.db.refresh(session)
        from app.workflows.drama.events import WorkflowEventPublisher
        WorkflowEventPublisher(self.db).publish(session, "session_created", {"source_chars": len(source_text)})
        return ContentAdaptationService(self.db).snapshot(session.id)

    def list(self, project_id: int | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        stmt = select(ChatSessionPO).where(ChatSessionPO.deleted_at.is_(None))
        if project_id:
            project = self.db.get(ProjectPO, project_id)
            if not project:
                return []
            # 防御旧版删除不完整 + SQLite 主键复用造成的跨项目会话污染。
            stmt = stmt.where(
                ChatSessionPO.project_id == project_id,
                ChatSessionPO.created_at >= project.created_at,
            )
        if status:
            stmt = stmt.where(ChatSessionPO.status == status)
        sessions = self.db.execute(stmt.order_by(ChatSessionPO.updated_at.desc()).limit(min(max(limit, 1), 200))).scalars()
        return [self._summary(item) for item in sessions]

    def get(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.source_type == "knowledge_article":
            from app.services.knowledge_production_service import KnowledgeProductionService
            return KnowledgeProductionService(self.db).snapshot(session_id)
        return ContentAdaptationService(self.db).snapshot(session_id)

    def history(self, session_id: str, limit: int = 100, before_id: str | None = None) -> list[dict[str, Any]]:
        self._session(session_id)
        stmt = select(ChatMessagePO).where(ChatMessagePO.session_id == session_id)
        if before_id:
            before = self.db.get(ChatMessagePO, before_id)
            if not before or before.session_id != session_id:
                raise ValueError("历史消息游标无效")
            stmt = stmt.where(ChatMessagePO.created_at < before.created_at)
        rows = list(self.db.execute(stmt.order_by(ChatMessagePO.created_at.desc()).limit(min(max(limit, 1), 200))).scalars())
        rows.reverse()
        return [{
            "id": row.id, "role": row.role, "message_type": row.message_type,
            "content": row.content, "payload": row.payload_json or {}, "created_at": row.created_at,
        } for row in rows]

    def events(self, session_id: str, after_sequence: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        self._session(session_id)
        rows = self.db.execute(
            select(WorkflowEventPO).where(
                WorkflowEventPO.session_id == session_id,
                WorkflowEventPO.sequence > after_sequence,
            ).order_by(WorkflowEventPO.sequence.asc()).limit(min(max(limit, 1), 200))
        ).scalars()
        return [{
            "event_id": row.id, "event_type": row.event_type, "session_id": row.session_id,
            "project_id": row.project_id, "sequence": row.sequence, "stage": row.stage,
            "payload": row.payload_json or {}, "created_at": row.created_at,
        } for row in rows]

    def cancel(self, session_id: str, client_request_id: str) -> dict[str, Any]:
        return DramaWorkflowService(self.db).submit_action(session_id, {
            "action": "cancel", "feedback": "", "payload": {}, "client_request_id": client_request_id,
        })

    def delete(self, session_id: str) -> None:
        session = self._session(session_id)
        session.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

    def _session(self, session_id: str) -> ChatSessionPO:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        return session

    @staticmethod
    def _summary(session: ChatSessionPO) -> dict[str, Any]:
        return {
            "session_id": session.id, "thread_id": session.id, "project_id": session.project_id,
            "chapter_id": session.chapter_id, "title": session.title, "status": session.status,
            "source_type": session.source_type, "adaptation_mode": session.adaptation_mode,
            "article_source_id": session.article_source_id,
            "current_stage": session.current_stage, "active_confirm_type": session.active_confirm_type,
            "last_error_code": session.last_error_code, "last_error_message": session.last_error_message,
            "updated_at": session.updated_at, "created_at": session.created_at,
        }
