from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import AdaptationRunPO, ChatMessagePO, ChatSessionPO
from app.services.drama_workflow_service import DramaWorkflowService
from app.workflows.content_types import KNOWLEDGE_ARTICLE_SOURCE_TYPE
from app.workflows.drama.events import WorkflowEventPublisher


class ContentAdaptationService:
    """Route a durable session to its content-specific workflow.

    Novel behavior remains delegated to ``DramaWorkflowService``. Phase 0 only
    establishes the article boundary and a recoverable ``source_ready`` state;
    article analysis is intentionally not implemented in the novel workflow.
    """

    def __init__(self, db: Session):
        self.db = db

    def start(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.source_type != KNOWLEDGE_ARTICLE_SOURCE_TYPE:
            return DramaWorkflowService(self.db).start(session_id)
        if session.current_stage != "created":
            return self.snapshot(session_id)

        run = self._run(session)
        session.current_stage = "source_ready"
        session.active_confirm_type = None
        session.last_error_code = None
        session.last_error_message = None
        run.current_stage = "source_ready"
        run.error_message = None
        self.db.commit()
        self.db.add(ChatMessagePO(
            id=f"msg_article_ready_{session.id}",
            session_id=session.id,
            role="assistant",
            message_type="status",
            content="文章正文已保存。文章分析能力将在下一阶段启用。",
            payload_json={"stage": "source_ready", "source_type": session.source_type},
        ))
        self.db.commit()
        WorkflowEventPublisher(self.db).publish(session, "article_source_ready", {
            "source_chars": len(session.source_text or ""),
        })
        return self.snapshot(session_id)

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.source_type != KNOWLEDGE_ARTICLE_SOURCE_TYPE:
            return DramaWorkflowService(self.db).snapshot(session_id)
        run = self._run(session)
        return {
            "session_id": session.id,
            "thread_id": session.id,
            "project_id": session.project_id,
            "chapter_id": session.chapter_id,
            "adaptation_run_id": session.adaptation_run_id,
            "title": session.title,
            "source_type": session.source_type,
            "adaptation_mode": session.adaptation_mode,
            "article_category": session.article_category,
            "learning_goal": session.learning_goal,
            "target_duration_minutes": session.target_duration_minutes,
            "verification_mode": session.verification_mode,
            "article_source_id": session.article_source_id,
            "status": session.status,
            "current_stage": session.current_stage,
            "active_confirm_type": session.active_confirm_type,
            "pending_confirm": session.pending_confirm_json,
            "last_error_code": session.last_error_code,
            "last_error_message": session.last_error_message,
            "article_analysis": run.article_analysis_json,
            "learning_plan": run.learning_plan_json,
            "knowledge_review": run.knowledge_review_json,
            "external_sources": run.external_sources_json or [],
            "source_text": session.source_text,
            "instruction": session.instruction,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "completed_at": session.completed_at,
        }

    def resume(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.source_type != KNOWLEDGE_ARTICLE_SOURCE_TYPE:
            return DramaWorkflowService(self.db).resume(session_id)
        if session.current_stage == "failed":
            retry_stage = (session.pending_confirm_json or {}).get("retry_stage")
            session.current_stage = "created"
            session.status = "active"
            session.last_error_code = None
            session.last_error_message = None
            session.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            if retry_stage == "analyzing_article":
                session.current_stage = "source_ready"
                self._run(session).current_stage = "source_ready"
                self.db.commit()
                from app.services.article_workflow_service import ArticleWorkflowService
                return ArticleWorkflowService(self.db).analyze(session_id)
            if retry_stage in {"designing_learning_plan", "learning_plan_ready", "generating_knowledge_script", "reviewing_knowledge_script"}:
                session.current_stage = "outline_ready"
                self._run(session).current_stage = "outline_ready"
                self.db.commit()
                from app.services.knowledge_production_service import KnowledgeProductionService
                return KnowledgeProductionService(self.db).generate_script(session_id)
            return self.start(session_id)
        return self.snapshot(session_id)

    def _session(self, session_id: str) -> ChatSessionPO:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        return session

    def _run(self, session: ChatSessionPO) -> AdaptationRunPO:
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        if not run:
            raise ValueError("会话关联的改编记录不存在")
        return run
