from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import DRAMA_WORKFLOW_MAX_ITERATIONS
from app.models.po import (
    AdaptationDraftRevisionPO,
    AdaptationRunPO,
    ChatMessagePO,
    ChatSessionPO,
    ProjectPO,
)
from app.services.role_draft_service import RoleDraftService
from app.services.script_draft_service import ScriptDraftService
from app.services.script_review_service import ScriptReviewService
from app.services.source_parser_service import SourceParserService
from app.services.workflow_llm_service import WorkflowLLMError
from app.workflows.drama.events import WorkflowEventPublisher
from app.workflows.drama.schemas import DramaScript, RoleDraftList, WorkflowAction


ACTION_STAGES = {
    "confirm_roles": {"awaiting_role_confirmation"},
    "revise_roles": {"awaiting_role_confirmation"},
    "confirm_script": {"awaiting_script_confirmation"},
    "revise_script": {"awaiting_script_confirmation"},
    "cancel": {
        "created", "parsing", "awaiting_role_confirmation", "generating_script",
        "reviewing_script", "awaiting_script_confirmation", "failed", "script_draft_ready",
    },
    "retry": {"failed"},
    "commit": {"script_draft_ready"},
}


class WorkflowConflictError(RuntimeError):
    pass


class DramaWorkflowService:
    """Database-backed workflow state machine for one-chapter adaptation.

    ``chat_sessions`` and ``adaptation_runs`` are the only durable state.  Each
    public command validates the current stage, acquires a short lease, performs
    one explicit transition, and persists the new stage before returning.
    """

    def __init__(self, db: Session):
        self.db = db
        self.source_parser = SourceParserService(db)
        self.role_drafter = RoleDraftService(db)
        self.script_drafter = ScriptDraftService(db)
        self.script_reviewer = ScriptReviewService(db)
        self.events = WorkflowEventPublisher(db)

    def start(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.current_stage not in {"created", "failed"}:
            return self.snapshot(session_id)
        return self._run_locked(session, lambda: self._start_pipeline(session))

    def submit_action(
        self,
        session_id: str,
        raw_action: dict[str, Any],
        *,
        record_user_message: bool = True,
    ) -> dict[str, Any]:
        action = WorkflowAction.model_validate(raw_action)
        session = self._session(session_id)
        self._validate_action(session, action.action)

        existing = self.db.execute(
            select(ChatMessagePO).where(
                ChatMessagePO.session_id == session_id,
                ChatMessagePO.client_request_id == action.client_request_id,
            )
        ).scalar_one_or_none()
        if existing and record_user_message:
            return self.snapshot(session_id)

        if record_user_message:
            self._add_message(
                session_id,
                "user",
                "confirm" if action.action.startswith("confirm") else "text",
                action.feedback or self._action_label(action.action),
                action.model_dump(),
                action.client_request_id,
            )

        return self._run_locked(session, lambda: self._dispatch(session, action))

    def resume(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.current_stage != "failed":
            return self.snapshot(session_id)
        return self.submit_action(session_id, {
            "action": "retry",
            "feedback": "",
            "payload": {},
            "client_request_id": f"retry-{uuid4().hex}",
        })

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        return {
            "session_id": session.id,
            "thread_id": session.id,
            "project_id": session.project_id,
            "chapter_id": session.chapter_id,
            "adaptation_run_id": session.adaptation_run_id,
            "title": session.title,
            "source_type": session.source_type,
            "adaptation_mode": session.adaptation_mode,
            "article_source_id": session.article_source_id,
            "status": session.status,
            "current_stage": session.current_stage,
            "active_confirm_type": session.active_confirm_type,
            "pending_confirm": session.pending_confirm_json,
            "last_error_code": session.last_error_code,
            "last_error_message": session.last_error_message,
            "role_drafts": self._latest_revision(session.id, "roles"),
            "script_draft": run.draft_json if run else None,
            "script_review": run.review_json if run else None,
            "draft_revision": run.draft_revision if run else 0,
            "script_revisions": self._script_revisions(session.id),
            "source_text": session.source_text,
            "instruction": session.instruction,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "completed_at": session.completed_at,
        }

    def _start_pipeline(self, session: ChatSessionPO) -> dict[str, Any]:
        _, run, project = self._context(session.id)
        self._set_stage(session, "parsing")
        parsed = self.source_parser.parse(project, session.source_text or "", session.instruction)
        run.parsed_json = parsed
        run.current_stage = "parsing"
        run.error_message = None
        self.db.commit()
        self._add_message(session.id, "assistant", "status", "小说解析完成，正在生成角色草稿。", {"stage": "parsing"})
        return self._generate_roles(session, previous_roles=None, feedback="")

    def _dispatch(self, session: ChatSessionPO, action: WorkflowAction) -> dict[str, Any]:
        if action.action == "confirm_roles":
            roles_payload = action.payload.get("roles") or (self._latest_revision(session.id, "roles") or {}).get("roles", [])
            roles = RoleDraftList.model_validate({"roles": roles_payload}).model_dump()["roles"]
            self._store_confirmed_roles(session.id, roles)
            return self._generate_script(session, roles=roles, previous_script=None, feedback="")
        if action.action == "revise_roles":
            previous = (self._latest_revision(session.id, "roles") or {}).get("roles", [])
            return self._generate_roles(session, previous_roles=previous, feedback=action.feedback)
        if action.action == "confirm_script":
            _, run, _ = self._context(session.id)
            script = action.payload.get("script") or run.draft_json or {}
            self._confirm_script(session, script)
            return self.snapshot(session.id)
        if action.action == "revise_script":
            _, run, _ = self._context(session.id)
            roles = self._confirmed_roles(session.id)
            return self._generate_script(
                session,
                roles=roles,
                previous_script=run.draft_json,
                feedback=action.feedback,
            )
        if action.action == "retry":
            return self._retry_failed(session)
        if action.action == "cancel":
            self._cancel(session)
            return self.snapshot(session.id)
        raise WorkflowConflictError(f"不支持的工作流动作: {action.action}")

    def _generate_roles(
        self,
        session: ChatSessionPO,
        previous_roles: list[dict[str, Any]] | None,
        feedback: str,
    ) -> dict[str, Any]:
        _, run, project = self._context(session.id)
        self._check_revision_limit(session.id, "roles")
        roles = self.role_drafter.generate(
            project,
            run.parsed_json or {},
            previous_roles or None,
            feedback,
        )
        revision = self._save_revision(session.id, run.id, "roles", {"roles": roles}, feedback)
        self._set_stage(
            session,
            "awaiting_role_confirmation",
            confirm_type="roles",
            pending={"type": "roles", "revision": revision, "roles": roles},
        )
        message = self._add_message(
            session.id,
            "assistant",
            "role_draft",
            "角色草稿已生成，请确认或提出修改。",
            {"roles": roles, "revision": revision},
        )
        self.events.publish(session, "role_draft_ready", {
            "message_id": message.id,
            "draft_revision": revision,
            "role_count": len(roles),
        })
        return self.snapshot(session.id)

    def _generate_script(
        self,
        session: ChatSessionPO,
        roles: list[dict[str, Any]],
        previous_script: dict[str, Any] | None,
        feedback: str,
    ) -> dict[str, Any]:
        _, run, project = self._context(session.id)
        self._check_revision_limit(session.id, "script")
        self._set_stage(session, "generating_script")
        script = self.script_drafter.generate(
            project,
            run.parsed_json or {},
            roles,
            session.source_text or "",
            session.instruction,
            previous_script,
            feedback,
        )
        label = "用户意见稿" if feedback else "初稿"
        source = "user_feedback" if feedback else "ai_initial"
        revision = self._save_script_revision(
            session.id, run.id, script, feedback, label=label, source=source, status="reviewing",
        )
        run.draft_json = script
        run.review_json = None
        run.draft_revision = revision
        run.status = "running"
        run.current_stage = "reviewing_script"
        self.db.commit()
        self._set_stage(session, "reviewing_script")
        self._add_message(
            session.id,
            "assistant",
            "status",
            f"{label}已生成，可以先阅读；AI 正在进行独立声音规范审查。",
            {"stage": "reviewing_script", "revision": revision, "label": label},
        )
        self.events.publish(session, "script_draft_generated", {
            "draft_revision": revision,
            "label": label,
            "review_status": "reviewing",
        })
        initial_review = self.script_reviewer.review(
            project,
            run.parsed_json or {},
            roles,
            session.source_text or "",
            script,
            self.script_drafter._narration_issues(script),
        )
        review = initial_review
        repair_applied = False
        self._update_script_revision(
            session.id,
            revision,
            review=initial_review,
            status="reviewed" if initial_review.get("passed") else "needs_repair",
        )
        if not initial_review.get("passed"):
            script = self.script_drafter.revise_from_review(
                project,
                run.parsed_json or {},
                roles,
                session.source_text or "",
                script,
                initial_review,
            )
            repair_applied = True
            revision = self._save_script_revision(
                session.id,
                run.id,
                script,
                feedback,
                label="AI 复核返修稿",
                source="ai_review_repair",
                status="reviewing",
            )
            run.draft_json = script
            run.review_json = None
            run.draft_revision = revision
            self.db.commit()
            self._add_message(
                session.id,
                "assistant",
                "status",
                "独立审查发现需要修正的内容，AI 返修稿已生成，可以与初稿对照；正在进行最终复核。",
                {"stage": "reviewing_script", "revision": revision, "label": "AI 复核返修稿"},
            )
            self.events.publish(session, "script_repair_generated", {
                "draft_revision": revision,
                "label": "AI 复核返修稿",
                "review_status": "reviewing",
            })
            review = self.script_reviewer.review(
                project,
                run.parsed_json or {},
                roles,
                session.source_text or "",
                script,
                self.script_drafter._narration_issues(script),
            )
        review["repair_applied"] = repair_applied
        review["initial_score"] = initial_review.get("score")
        self._update_script_revision(session.id, revision, review=review, status="reviewed")
        run.draft_json = script
        run.review_json = review
        run.draft_revision = revision
        run.status = "script_ready"
        run.current_stage = "awaiting_script_confirmation"
        self._set_stage(
            session,
            "awaiting_script_confirmation",
            confirm_type="script",
            pending={"type": "script", "revision": revision},
        )
        line_count = sum(len(scene.get("lines", [])) for scene in script.get("scenes", []))
        issue_count = len(review.get("issues") or [])
        review_message = (
            "剧本草稿已通过独立声音规范审查，请按场景检查。"
            if review.get("passed")
            else f"剧本草稿已完成独立审查，仍有 {issue_count} 项提示，请结合审查报告检查。"
        )
        message = self._add_message(
            session.id,
            "assistant",
            "script_draft",
            review_message,
            {"script": script, "review": review, "revision": revision},
        )
        self.events.publish(session, "script_draft_ready", {
            "message_id": message.id,
            "draft_revision": revision,
            "line_count": line_count,
            "review_passed": bool(review.get("passed")),
            "review_score": review.get("score"),
        })
        return self.snapshot(session.id)

    def _confirm_script(self, session: ChatSessionPO, script: dict[str, Any]) -> None:
        _, run, _ = self._context(session.id)
        validated = DramaScript.model_validate(script).model_dump()
        run.draft_json = validated
        run.final_json = validated
        run.status = "script_ready"
        run.current_stage = "script_draft_ready"
        self._set_stage(session, "script_draft_ready")
        self._add_message(
            session.id,
            "assistant",
            "confirm",
            "剧本已确认，可以安全写入项目。",
            {"draft_revision": run.draft_revision},
        )
        self.events.publish(session, "awaiting_confirmation", {
            "confirm_type": "commit",
            "draft_revision": run.draft_revision,
        })

    def _retry_failed(self, session: ChatSessionPO) -> dict[str, Any]:
        retry_stage = (session.pending_confirm_json or {}).get("retry_stage") or "parsing"
        session.status = "active"
        if retry_stage in {"created", "parsing"}:
            return self._start_pipeline(session)
        if retry_stage in {"awaiting_role_confirmation"}:
            previous = (self._latest_revision(session.id, "roles") or {}).get("roles", [])
            return self._generate_roles(session, previous_roles=previous, feedback="")
        if retry_stage in {"generating_script", "awaiting_script_confirmation"}:
            _, run, _ = self._context(session.id)
            return self._generate_script(
                session,
                roles=self._confirmed_roles(session.id),
                previous_script=run.draft_json,
                feedback="",
            )
        raise WorkflowConflictError(f"阶段 {retry_stage} 无法自动重试")

    def _cancel(self, session: ChatSessionPO) -> None:
        session.status = "cancelled"
        session.current_stage = "cancelled"
        session.active_confirm_type = None
        session.pending_confirm_json = None
        self.db.commit()
        self._add_message(session.id, "assistant", "status", "本次改编会话已取消。")
        self.events.publish(session, "workflow_cancelled")

    def _set_stage(
        self,
        session: ChatSessionPO,
        stage: str,
        *,
        confirm_type: str | None = None,
        pending: dict[str, Any] | None = None,
    ) -> None:
        session.status = "active"
        session.current_stage = stage
        session.active_confirm_type = confirm_type
        session.pending_confirm_json = pending
        session.last_error_code = None
        session.last_error_message = None
        self.db.commit()
        event_type = "awaiting_confirmation" if confirm_type else "stage_started"
        self.events.publish(session, event_type, {"confirm_type": confirm_type} if confirm_type else {"stage": stage})

    def _run_locked(self, session: ChatSessionPO, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        token = self._acquire_lease(session)
        try:
            return operation()
        except Exception as exc:
            failed_stage = session.current_stage
            logging.exception("对话式改编失败: session=%s stage=%s", session.id, failed_stage)
            self._mark_failed(session.id, exc, failed_stage)
            raise
        finally:
            self._release_lease(session.id, token)

    def _mark_failed(self, session_id: str, exc: Exception, failed_stage: str) -> None:
        self.db.rollback()
        session = self._session(session_id)
        code = getattr(exc, "code", None) or (
            "WORKFLOW_CONFLICT" if isinstance(exc, WorkflowConflictError) else "WORKFLOW_FAILED"
        )
        message = str(exc) if isinstance(exc, (WorkflowLLMError, WorkflowConflictError, ValueError)) else "当前步骤执行失败，请重试"
        session.status = "failed"
        session.current_stage = "failed"
        session.last_error_code = code
        session.last_error_message = message
        session.active_confirm_type = None
        session.pending_confirm_json = {"type": "retry", "retry_stage": failed_stage}
        if session.adaptation_run_id:
            run = self.db.get(AdaptationRunPO, session.adaptation_run_id)
            if run:
                run.status = "failed"
                run.current_stage = "failed"
                run.error_message = message
        self.db.commit()
        self._add_message(session.id, "assistant", "error", message, {
            "error_code": code,
            "retry_stage": failed_stage,
        })
        self.events.publish(session, "workflow_failed", {
            "error_code": code,
            "message": message,
            "retry_stage": failed_stage,
        })

    def _store_confirmed_roles(self, session_id: str, roles: list[dict[str, Any]]) -> None:
        revision = self._latest_revision_row(session_id, "roles")
        if not revision:
            raise WorkflowConflictError("没有可确认的角色草稿")
        revision.payload_json = {"roles": roles, "confirmed": True}
        self.db.commit()

    def _confirmed_roles(self, session_id: str) -> list[dict[str, Any]]:
        payload = self._latest_revision(session_id, "roles") or {}
        roles = payload.get("roles", [])
        return [role for role in roles if role.get("selected", True)]

    def _context(self, session_id: str) -> tuple[ChatSessionPO, AdaptationRunPO, ProjectPO]:
        session = self._session(session_id)
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        project = self.db.get(ProjectPO, session.project_id)
        if not run or not project:
            raise ValueError("会话关联的项目或改编记录不存在")
        return session, run, project

    def _session(self, session_id: str) -> ChatSessionPO:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        return session

    def _validate_action(self, session: ChatSessionPO, action: str) -> None:
        if session.status in {"completed", "cancelled"}:
            raise WorkflowConflictError("该会话已经结束")
        if session.current_stage not in ACTION_STAGES.get(action, set()):
            raise WorkflowConflictError(f"当前阶段 {session.current_stage} 不允许执行 {action}")
        expected = "roles" if action.endswith("roles") else "script" if action.endswith("script") else None
        if expected and session.active_confirm_type != expected:
            raise WorkflowConflictError("确认动作与当前待确认内容不匹配")

    def _add_message(
        self,
        session_id: str,
        role: str,
        message_type: str,
        content: str | None,
        payload: dict[str, Any] | None = None,
        client_request_id: str | None = None,
    ) -> ChatMessagePO:
        message = ChatMessagePO(
            id=f"msg_{uuid4().hex}",
            session_id=session_id,
            role=role,
            message_type=message_type,
            content=content,
            payload_json=payload or {},
            client_request_id=client_request_id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def _save_revision(
        self,
        session_id: str,
        run_id: int,
        draft_type: str,
        payload: dict[str, Any],
        feedback: str | None,
    ) -> int:
        current = self.db.execute(
            select(func.max(AdaptationDraftRevisionPO.revision)).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == draft_type,
            )
        ).scalar_one_or_none() or 0
        revision = current + 1
        self.db.add(AdaptationDraftRevisionPO(
            session_id=session_id,
            run_id=run_id,
            draft_type=draft_type,
            revision=revision,
            payload_json=payload,
            feedback=feedback or None,
        ))
        self.db.commit()
        return revision

    def _save_script_revision(
        self,
        session_id: str,
        run_id: int,
        script: dict[str, Any],
        feedback: str | None,
        *,
        label: str,
        source: str,
        status: str,
    ) -> int:
        return self._save_revision(session_id, run_id, "script", {
            "script": script,
            "label": label,
            "source": source,
            "status": status,
            "review": None,
        }, feedback)

    def _update_script_revision(
        self,
        session_id: str,
        revision: int,
        *,
        review: dict[str, Any],
        status: str,
    ) -> None:
        row = self.db.execute(
            select(AdaptationDraftRevisionPO).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == "script",
                AdaptationDraftRevisionPO.revision == revision,
            )
        ).scalar_one()
        payload = dict(row.payload_json or {})
        if "script" not in payload:
            payload = {
                "script": payload,
                "label": f"草稿版本 {revision}",
                "source": "legacy",
            }
        payload["review"] = review
        payload["status"] = status
        row.payload_json = payload
        self.db.commit()

    def _script_revisions(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(AdaptationDraftRevisionPO).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == "script",
            ).order_by(AdaptationDraftRevisionPO.revision.asc())
        ).scalars().all()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row.payload_json or {}
            is_envelope = isinstance(payload, dict) and isinstance(payload.get("script"), dict)
            result.append({
                "revision": row.revision,
                "label": payload.get("label") if is_envelope else f"草稿版本 {row.revision}",
                "source": payload.get("source") if is_envelope else "legacy",
                "status": payload.get("status", "reviewed") if is_envelope else "reviewed",
                "review": payload.get("review") if is_envelope else None,
                "script": payload.get("script") if is_envelope else payload,
                "feedback": row.feedback,
                "created_at": row.created_at,
            })
        return result

    def _latest_revision_row(self, session_id: str, draft_type: str) -> AdaptationDraftRevisionPO | None:
        return self.db.execute(
            select(AdaptationDraftRevisionPO).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == draft_type,
            ).order_by(AdaptationDraftRevisionPO.revision.desc()).limit(1)
        ).scalar_one_or_none()

    def _latest_revision(self, session_id: str, draft_type: str):
        revision = self._latest_revision_row(session_id, draft_type)
        return revision.payload_json if revision else None

    def _check_revision_limit(self, session_id: str, draft_type: str) -> None:
        count = self.db.execute(
            select(func.count(AdaptationDraftRevisionPO.id)).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == draft_type,
            )
        ).scalar_one()
        if count >= DRAMA_WORKFLOW_MAX_ITERATIONS:
            label = "角色" if draft_type == "roles" else "剧本"
            raise WorkflowConflictError(f"{label}草稿已达到最大修改次数，请手动编辑后确认")

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

    @staticmethod
    def _action_label(action: str) -> str:
        return {
            "confirm_roles": "确认角色并生成剧本",
            "confirm_script": "确认剧本",
            "retry": "重试当前步骤",
            "cancel": "取消会话",
        }.get(action, action)
