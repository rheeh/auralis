from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.po import AdaptationDraftRevisionPO, AdaptationRunPO
from app.services.article_workflow_service import ArticleWorkflowService
from app.services.drama_workflow_service import WorkflowConflictError
from app.services.knowledge_review_service import KnowledgeReviewService
from app.services.knowledge_script_service import KnowledgeScriptService
from app.services.learning_design_service import LearningDesignService
from app.workflows.article.schemas import KnowledgeScript, LearningPlan


class KnowledgeProductionService(ArticleWorkflowService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.learning_designer = LearningDesignService(db)
        self.script_writer = KnowledgeScriptService(db)
        self.reviewer = KnowledgeReviewService(db)

    def generate_script(self, session_id: str) -> dict[str, Any]:
        session, run, project = self._context(session_id)
        if session.current_stage == "awaiting_script_confirmation" and run.draft_json:
            return self.snapshot(session_id)
        if session.current_stage not in {"outline_ready", "learning_plan_ready", "failed"}:
            raise WorkflowConflictError(f"当前阶段 {session.current_stage} 不能生成知识脚本")
        token = self._acquire_lease(session)
        try:
            analysis = run.article_analysis_json or {}
            if not run.learning_plan_json:
                self._set_stage(session, run, "designing_learning_plan")
                plan = self.learning_designer.generate(
                    project, analysis, session.learning_goal or "quick_understanding",
                    session.target_duration_minutes or 10, session.adaptation_mode or "auto",
                )
                run.learning_plan_json = plan
                self._set_stage(session, run, "learning_plan_ready")
                self._add_message(session.id, "assistant", "learning_plan", "知识音频的学习结构已设计完成。", {"learning_plan": plan})
            else:
                plan = LearningPlan.model_validate(run.learning_plan_json).model_dump(mode="json")

            self._set_stage(session, run, "generating_knowledge_script")
            script = self.script_writer.generate(
                project,
                analysis,
                plan,
                session.instruction,
                prior_learning_context=self._prior_learning_context(project.id, session.id),
            )
            run.draft_json = script
            revision = self._save_script_revision(session.id, run.id, script, feedback=None, status="reviewing")
            self._set_stage(session, run, "reviewing_knowledge_script")
            self._add_message(session.id, "assistant", "knowledge_script", "知识音频初稿已生成，独立审查正在进行。", {"revision": revision, "script": script})
            self.events.publish(session, "knowledge_script_initial_ready", {"revision": revision})

            review = self.reviewer.review(project, session.source_text or "", analysis, script)
            run.knowledge_review_json = review
            run.review_json = review
            self._update_script_revision(session.id, revision, review, status="reviewed")
            session.pending_confirm_json = {"type": "knowledge_script", "revision": revision}
            self._set_stage(session, run, "awaiting_script_confirmation", confirm_type="knowledge_script")
            self._add_message(session.id, "assistant", "knowledge_review", "内容准确性、学习质量和音频表现审查已完成。", {"revision": revision, "review": review})
            self.events.publish(session, "knowledge_script_reviewed", {"revision": revision, "passed": review["passed"]})
            return self.snapshot(session_id)
        except Exception as exc:
            self._fail(session, run, exc, session.current_stage)
            raise
        finally:
            self._release_lease(session_id, token)

    def revise_script(self, session_id: str, feedback: str, client_request_id: str) -> dict[str, Any]:
        session, run, project = self._context(session_id)
        self._require_script_confirmation(session)
        if self._request_exists(session_id, client_request_id):
            return self.snapshot(session_id)
        if not feedback.strip():
            raise ValueError("请提供知识脚本修改意见")
        token = self._acquire_lease(session)
        try:
            self._add_message(session.id, "user", "text", feedback, {}, client_request_id)
            self._set_stage(session, run, "generating_knowledge_script")
            script = self.script_writer.revise(
                project, run.article_analysis_json or {}, run.learning_plan_json or {}, run.draft_json or {}, feedback,
            )
            run.draft_json = script
            revision = self._save_script_revision(session.id, run.id, script, feedback=feedback, status="reviewing")
            self._set_stage(session, run, "reviewing_knowledge_script")
            self._add_message(session.id, "assistant", "knowledge_script", "知识脚本已按意见修改，正在重新审查。", {"revision": revision, "script": script})
            review = self.reviewer.review(project, session.source_text or "", run.article_analysis_json or {}, script)
            run.knowledge_review_json = review
            run.review_json = review
            self._update_script_revision(session.id, revision, review, status="reviewed")
            session.pending_confirm_json = {"type": "knowledge_script", "revision": revision}
            self._set_stage(session, run, "awaiting_script_confirmation", confirm_type="knowledge_script")
            self.events.publish(session, "knowledge_script_revised", {"revision": revision, "passed": review["passed"]})
            return self.snapshot(session_id)
        except Exception as exc:
            self._fail(session, run, exc, session.current_stage)
            raise
        finally:
            self._release_lease(session_id, token)

    def confirm_script(self, session_id: str, payload: dict[str, Any], client_request_id: str) -> dict[str, Any]:
        session, run, _ = self._context(session_id)
        if session.current_stage == "knowledge_script_ready":
            return self.snapshot(session_id)
        self._require_script_confirmation(session)
        if self._request_exists(session_id, client_request_id):
            return self.snapshot(session_id)
        script = KnowledgeScript.model_validate(payload.get("script") or run.draft_json or {}).model_dump(mode="json")
        run.draft_json = script
        run.final_json = script
        session.pending_confirm_json = None
        self._set_stage(session, run, "knowledge_script_ready")
        self._add_message(session.id, "user", "confirm", "确认知识音频脚本", {}, client_request_id)
        self.events.publish(session, "knowledge_script_confirmed", {"review_question_count": len(script["review_questions"])})
        return self.snapshot(session_id)

    def snapshot(self, session_id: str) -> dict[str, Any]:
        base = super().snapshot(session_id)
        _, run, _ = self._context(session_id)
        base.update({
            "learning_plan": run.learning_plan_json,
            "knowledge_script": run.draft_json,
            "knowledge_review": run.knowledge_review_json,
            "knowledge_script_revisions": self._script_revisions(session_id),
            "review_questions": (run.draft_json or {}).get("review_questions", []),
        })
        return base

    def _save_script_revision(self, session_id: str, run_id: int, script: dict[str, Any], feedback: str | None, status: str) -> int:
        revision = self.db.scalar(select(func.max(AdaptationDraftRevisionPO.revision)).where(
            AdaptationDraftRevisionPO.session_id == session_id,
            AdaptationDraftRevisionPO.draft_type == "knowledge_script",
        )) or 0
        revision += 1
        self.db.add(AdaptationDraftRevisionPO(
            session_id=session_id, run_id=run_id, draft_type="knowledge_script", revision=revision,
            payload_json={"script": script, "status": status, "review": None}, feedback=feedback or None,
        ))
        self.db.commit()
        return revision

    def _update_script_revision(self, session_id: str, revision: int, review: dict[str, Any], status: str) -> None:
        row = self.db.execute(select(AdaptationDraftRevisionPO).where(
            AdaptationDraftRevisionPO.session_id == session_id,
            AdaptationDraftRevisionPO.draft_type == "knowledge_script",
            AdaptationDraftRevisionPO.revision == revision,
        )).scalar_one()
        payload = dict(row.payload_json or {})
        payload.update(review=review, status=status)
        row.payload_json = payload
        self.db.commit()

    def _script_revisions(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(select(AdaptationDraftRevisionPO).where(
            AdaptationDraftRevisionPO.session_id == session_id,
            AdaptationDraftRevisionPO.draft_type == "knowledge_script",
        ).order_by(AdaptationDraftRevisionPO.revision.asc())).scalars().all()
        return [{"revision": row.revision, "script": (row.payload_json or {}).get("script"), "status": (row.payload_json or {}).get("status"), "review": (row.payload_json or {}).get("review"), "feedback": row.feedback, "created_at": row.created_at} for row in rows]

    def _prior_learning_context(self, project_id: int, session_id: str) -> list[dict[str, Any]]:
        """Bounded, source-grounded memory for the recurring learning partners."""
        runs = self.db.execute(
            select(AdaptationRunPO).where(
                AdaptationRunPO.project_id == project_id,
                AdaptationRunPO.source_kind == "knowledge_article",
                AdaptationRunPO.session_id != session_id,
                AdaptationRunPO.article_analysis_json.is_not(None),
            ).order_by(AdaptationRunPO.updated_at.desc()).limit(6)
        ).scalars().all()
        context: list[dict[str, Any]] = []
        for run in runs:
            analysis = run.article_analysis_json or {}
            context.append({
                "title": analysis.get("title") or run.title,
                "summary": analysis.get("summary", ""),
                "key_points": [
                    point.get("one_sentence_summary") or point.get("title")
                    for point in (analysis.get("key_points") or [])[:5]
                ],
            })
        return context

    @staticmethod
    def _require_script_confirmation(session) -> None:
        if session.current_stage != "awaiting_script_confirmation" or session.active_confirm_type != "knowledge_script":
            raise WorkflowConflictError("当前没有待确认的知识音频脚本")
