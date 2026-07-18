from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.po import AdaptationDraftRevisionPO, AdaptationRunPO, ChatMessagePO, ChatSessionPO, ProjectPO
from app.services.article_analysis_service import ArticleAnalysisService
from app.services.content_adaptation_service import ContentAdaptationService
from app.services.drama_workflow_service import WorkflowConflictError
from app.services.workflow_llm_service import WorkflowLLMError
from app.workflows.article.schemas import ArticleAnalysis
from app.workflows.drama.events import WorkflowEventPublisher


class ArticleWorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.analyzer = ArticleAnalysisService(db)
        self.events = WorkflowEventPublisher(db)

    def analyze(self, session_id: str) -> dict[str, Any]:
        session, run, project = self._context(session_id)
        if session.current_stage == "awaiting_outline_confirmation" and run.article_analysis_json:
            return self.snapshot(session_id)
        if session.current_stage not in {"source_ready", "failed"}:
            raise WorkflowConflictError(f"当前阶段 {session.current_stage} 不能分析文章")
        token = self._acquire_lease(session)
        try:
            self._set_stage(session, run, "analyzing_article")
            analysis = self.analyzer.analyze(
                project,
                session.source_text or "",
                article_category=session.article_category or "auto",
                learning_goal=session.learning_goal or "quick_understanding",
                target_duration_minutes=session.target_duration_minutes or 10,
                instruction=session.instruction,
            )
            run.article_analysis_json = analysis
            revision = self._save_outline_revision(session, run, analysis, feedback=None, confirmed=False)
            session.pending_confirm_json = {"type": "outline", "revision": revision}
            self._set_stage(session, run, "awaiting_outline_confirmation", confirm_type="outline")
            self._add_message(session.id, "assistant", "article_analysis", "文章分析和知识大纲已生成，请检查每个知识点的原文依据。", {"revision": revision, "analysis": analysis})
            self.events.publish(session, "article_outline_ready", {"revision": revision, "knowledge_point_count": len(analysis["key_points"])})
            return self.snapshot(session_id)
        except Exception as exc:
            self._fail(session, run, exc, "analyzing_article")
            raise
        finally:
            self._release_lease(session_id, token)

    def confirm_outline(self, session_id: str, payload: dict[str, Any], client_request_id: str) -> dict[str, Any]:
        session, run, _ = self._context(session_id)
        if session.current_stage == "outline_ready":
            return self.snapshot(session_id)
        self._require_outline_confirmation(session)
        if self._request_exists(session_id, client_request_id):
            return self.snapshot(session_id)
        analysis_payload = payload.get("analysis") or run.article_analysis_json or {}
        analysis = ArticleAnalysis.model_validate(analysis_payload).model_dump(mode="json")
        run.article_analysis_json = analysis
        revision = self._save_outline_revision(session, run, analysis, feedback=None, confirmed=True)
        session.pending_confirm_json = None
        self._set_stage(session, run, "outline_ready")
        self._add_message(session.id, "user", "confirm", "确认知识大纲", {"revision": revision}, client_request_id)
        self.events.publish(session, "article_outline_confirmed", {"revision": revision})
        return self.snapshot(session_id)

    def revise_outline(
        self,
        session_id: str,
        feedback: str,
        payload: dict[str, Any],
        client_request_id: str,
    ) -> dict[str, Any]:
        session, run, project = self._context(session_id)
        self._require_outline_confirmation(session)
        if self._request_exists(session_id, client_request_id):
            return self.snapshot(session_id)
        if not feedback.strip() and not payload.get("analysis"):
            raise ValueError("请提供大纲修改意见或修改后的完整分析")
        token = self._acquire_lease(session)
        try:
            self._add_message(session.id, "user", "text", feedback or "手动修改知识大纲", payload, client_request_id)
            if payload.get("analysis"):
                analysis = ArticleAnalysis.model_validate(payload["analysis"]).model_dump(mode="json")
            else:
                self._set_stage(session, run, "analyzing_article")
                analysis = self.analyzer.revise(project, session.source_text or "", run.article_analysis_json or {}, feedback)
            run.article_analysis_json = analysis
            revision = self._save_outline_revision(session, run, analysis, feedback=feedback, confirmed=False)
            session.pending_confirm_json = {"type": "outline", "revision": revision}
            self._set_stage(session, run, "awaiting_outline_confirmation", confirm_type="outline")
            self._add_message(session.id, "assistant", "article_analysis", "知识大纲已按意见更新。", {"revision": revision, "analysis": analysis})
            self.events.publish(session, "article_outline_revised", {"revision": revision})
            return self.snapshot(session_id)
        except Exception as exc:
            self._fail(session, run, exc, "analyzing_article")
            raise
        finally:
            self._release_lease(session_id, token)

    def snapshot(self, session_id: str) -> dict[str, Any]:
        base = ContentAdaptationService(self.db).snapshot(session_id)
        base["outline_revisions"] = self._outline_revisions(session_id)
        return base

    def _save_outline_revision(self, session: ChatSessionPO, run: AdaptationRunPO, analysis: dict[str, Any], feedback: str | None, confirmed: bool) -> int:
        revision = self.db.scalar(select(func.max(AdaptationDraftRevisionPO.revision)).where(
            AdaptationDraftRevisionPO.session_id == session.id,
            AdaptationDraftRevisionPO.draft_type == "article_outline",
        )) or 0
        revision += 1
        self.db.add(AdaptationDraftRevisionPO(
            session_id=session.id, run_id=run.id, draft_type="article_outline", revision=revision,
            payload_json={"analysis": analysis, "confirmed": confirmed}, feedback=feedback or None,
        ))
        self.db.commit()
        return revision

    def _outline_revisions(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(select(AdaptationDraftRevisionPO).where(
            AdaptationDraftRevisionPO.session_id == session_id,
            AdaptationDraftRevisionPO.draft_type == "article_outline",
        ).order_by(AdaptationDraftRevisionPO.revision.asc())).scalars().all()
        return [{"revision": row.revision, "analysis": (row.payload_json or {}).get("analysis"), "confirmed": bool((row.payload_json or {}).get("confirmed")), "feedback": row.feedback, "created_at": row.created_at} for row in rows]

    def _context(self, session_id: str) -> tuple[ChatSessionPO, AdaptationRunPO, ProjectPO]:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None or session.source_type != "knowledge_article":
            raise ValueError("知识文章会话不存在")
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        project = self.db.get(ProjectPO, session.project_id)
        if not run or not project:
            raise ValueError("会话关联的项目或改编记录不存在")
        return session, run, project

    @staticmethod
    def _require_outline_confirmation(session: ChatSessionPO) -> None:
        if session.current_stage != "awaiting_outline_confirmation" or session.active_confirm_type != "outline":
            raise WorkflowConflictError("当前没有待确认的知识大纲")

    def _request_exists(self, session_id: str, client_request_id: str) -> bool:
        return self.db.execute(select(ChatMessagePO.id).where(
            ChatMessagePO.session_id == session_id,
            ChatMessagePO.client_request_id == client_request_id,
        )).first() is not None

    def _set_stage(self, session: ChatSessionPO, run: AdaptationRunPO, stage: str, confirm_type: str | None = None) -> None:
        session.current_stage = stage
        session.active_confirm_type = confirm_type
        session.last_error_code = None
        session.last_error_message = None
        run.current_stage = stage
        run.status = "running"
        run.error_message = None
        self.db.commit()
        self.events.publish(session, "article_stage_changed", {"stage": stage})

    def _add_message(self, session_id: str, role: str, message_type: str, content: str, payload: dict[str, Any], client_request_id: str | None = None) -> None:
        self.db.add(ChatMessagePO(
            id=f"msg_{uuid4().hex}", session_id=session_id, role=role, message_type=message_type,
            content=content, payload_json=payload, client_request_id=client_request_id,
        ))
        self.db.commit()

    def _fail(self, session: ChatSessionPO, run: AdaptationRunPO, exc: Exception, stage: str) -> None:
        code = exc.code if isinstance(exc, WorkflowLLMError) else "ARTICLE_ANALYSIS_FAILED"
        message = str(exc) if isinstance(exc, (WorkflowLLMError, ValueError)) else "文章分析失败，请重试当前步骤"
        session.current_stage = "failed"
        session.active_confirm_type = None
        session.last_error_code = code
        session.last_error_message = message
        session.pending_confirm_json = {"retry_stage": stage}
        run.current_stage = "failed"
        run.status = "failed"
        run.error_message = message
        self.db.commit()
        self.events.publish(session, "article_workflow_failed", {"error_code": code, "message": message, "retry_stage": stage})

    def _acquire_lease(self, session: ChatSessionPO) -> str:
        now = datetime.now(timezone.utc)
        expires = session.lease_expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if session.running_token and expires and expires > now:
            raise WorkflowConflictError("该会话正在执行，请勿重复提交")
        token = uuid4().hex
        session.running_token = token
        session.lease_expires_at = now + timedelta(minutes=30)
        self.db.commit()
        return token

    def _release_lease(self, session_id: str, token: str) -> None:
        self.db.rollback()
        session = self.db.get(ChatSessionPO, session_id)
        if session and session.running_token == token:
            session.running_token = None
            session.lease_expires_at = None
            self.db.commit()
