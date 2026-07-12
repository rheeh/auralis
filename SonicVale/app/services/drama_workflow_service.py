from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import DRAMA_GRAPH_MAX_ITERATIONS
from app.models.po import (
    AdaptationDraftRevisionPO,
    AdaptationRunPO,
    ChatMessagePO,
    ChatSessionPO,
    ProjectPO,
)
from app.services.role_draft_service import RoleDraftService
from app.services.script_draft_service import ScriptDraftService
from app.services.source_parser_service import SourceParserService
from app.services.workflow_llm_service import WorkflowLLMError
from app.workflows.drama.checkpoint import open_drama_checkpointer
from app.workflows.drama.events import WorkflowEventPublisher
from app.workflows.drama.graph import build_drama_graph
from app.workflows.drama.schemas import DramaScript, RoleDraftList, WorkflowAction
from app.workflows.drama.state import DramaWorkflowState


ACTION_STAGES = {
    "confirm_roles": {"awaiting_role_confirmation"},
    "revise_roles": {"awaiting_role_confirmation"},
    "confirm_script": {"awaiting_script_confirmation"},
    "revise_script": {"awaiting_script_confirmation"},
    "cancel": {"created", "parsing", "awaiting_role_confirmation", "generating_script", "awaiting_script_confirmation", "failed", "script_draft_ready"},
    "retry": {"failed"},
    "commit": {"script_draft_ready"},
}


class WorkflowConflictError(RuntimeError):
    pass


class DramaWorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.source_parser = SourceParserService(db)
        self.role_drafter = RoleDraftService(db)
        self.script_drafter = ScriptDraftService(db)
        self.events = WorkflowEventPublisher(db)

    def start(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        state: DramaWorkflowState = {
            "session_id": session.id,
            "project_id": session.project_id,
            "chapter_id": session.chapter_id,
            "source_document_id": session.source_document_id,
            "source_text_ref": f"chat_sessions:{session.id}",
            "user_instruction": session.instruction,
            "current_stage": "created",
            "role_drafts": [],
            "confirmed_roles": [],
            "iteration_count": 0,
        }
        return self._invoke(session, state)

    def submit_action(self, session_id: str, raw_action: dict[str, Any]) -> dict[str, Any]:
        action = WorkflowAction.model_validate(raw_action)
        session = self._session(session_id)
        self._validate_action(session, action.action)

        existing = self.db.execute(
            select(ChatMessagePO).where(
                ChatMessagePO.session_id == session_id,
                ChatMessagePO.client_request_id == action.client_request_id,
            )
        ).scalar_one_or_none()
        if existing:
            return self.snapshot(session_id)

        self._add_message(
            session_id,
            "user",
            "confirm" if action.action.startswith("confirm") else "text",
            action.feedback or self._action_label(action.action),
            action.model_dump(),
            action.client_request_id,
        )
        if action.action == "retry":
            return self._invoke(session, None)
        if action.action == "cancel" and session.current_stage == "failed":
            self.mark_cancelled({"session_id": session.id})
            return self.snapshot(session_id)
        return self._invoke(session, Command(resume=action.model_dump()))

    def resume(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if session.current_stage == "failed":
            return self._invoke(session, None)
        return self.snapshot(session_id)

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
            "status": session.status,
            "current_stage": session.current_stage,
            "active_confirm_type": session.active_confirm_type,
            "pending_confirm": session.pending_confirm_json,
            "last_error_code": session.last_error_code,
            "last_error_message": session.last_error_message,
            "role_drafts": self._latest_revision(session.id, "roles"),
            "script_draft": run.draft_json if run else None,
            "draft_revision": run.draft_revision if run else 0,
            "source_text": session.source_text,
            "instruction": session.instruction,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "completed_at": session.completed_at,
        }

    def update_stage(self, state: DramaWorkflowState, stage: str, confirm_type: str | None = None) -> None:
        session = self._session(state["session_id"])
        session.status = "active"
        session.current_stage = stage
        session.active_confirm_type = confirm_type
        session.last_error_code = None
        session.last_error_message = None
        self.db.commit()
        event_type = "awaiting_confirmation" if confirm_type else "stage_started"
        self.events.publish(session, event_type, {"confirm_type": confirm_type} if confirm_type else {"stage": stage})

    def parse_source(self, state: DramaWorkflowState) -> dict[str, Any]:
        session, run, project = self._context(state["session_id"])
        parsed = self.source_parser.parse(project, session.source_text or "", session.instruction)
        run.parsed_json = parsed
        run.current_stage = "parsing"
        self.db.commit()
        self._add_message(session.id, "assistant", "status", "小说解析完成，正在生成角色草稿。", {"stage": "parsing"})
        return parsed

    def draft_roles(self, state: DramaWorkflowState) -> tuple[list[dict[str, Any]], int]:
        if state.get("iteration_count", 0) >= DRAMA_GRAPH_MAX_ITERATIONS:
            raise WorkflowConflictError("角色草稿已达到最大修改次数，请手动编辑后确认")
        session, run, project = self._context(state["session_id"])
        roles = self.role_drafter.generate(
            project,
            state.get("parsed_source") or run.parsed_json or {},
            state.get("role_drafts") or None,
            state.get("user_feedback") or "",
        )
        revision = self._save_revision(session.id, run.id, "roles", {"roles": roles}, state.get("user_feedback"))
        session.current_stage = "awaiting_role_confirmation"
        session.active_confirm_type = "roles"
        session.pending_confirm_json = {"type": "roles", "revision": revision, "roles": roles}
        self.db.commit()
        message = self._add_message(session.id, "assistant", "role_draft", "角色草稿已生成，请确认或提出修改。", {"roles": roles, "revision": revision})
        self.events.publish(session, "role_draft_ready", {"message_id": message.id, "draft_revision": revision, "role_count": len(roles)})
        return roles, revision

    def draft_script(self, state: DramaWorkflowState) -> tuple[dict[str, Any], int]:
        if state.get("iteration_count", 0) >= DRAMA_GRAPH_MAX_ITERATIONS:
            raise WorkflowConflictError("剧本草稿已达到最大修改次数，请手动编辑后确认")
        session, run, project = self._context(state["session_id"])
        script = self.script_drafter.generate(
            project,
            state.get("parsed_source") or run.parsed_json or {},
            state.get("confirmed_roles") or [],
            session.source_text or "",
            session.instruction,
            state.get("script_draft"),
            state.get("user_feedback") or "",
        )
        revision = self._save_revision(session.id, run.id, "script", script, state.get("user_feedback"))
        run.draft_json = script
        run.draft_revision = revision
        run.status = "script_ready"
        run.current_stage = "awaiting_script_confirmation"
        session.current_stage = "awaiting_script_confirmation"
        session.active_confirm_type = "script"
        session.pending_confirm_json = {"type": "script", "revision": revision}
        self.db.commit()
        line_count = sum(len(scene.get("lines", [])) for scene in script.get("scenes", []))
        message = self._add_message(session.id, "assistant", "script_draft", "剧本草稿已生成，请按场景检查。", {"script": script, "revision": revision})
        self.events.publish(session, "script_draft_ready", {"message_id": message.id, "draft_revision": revision, "line_count": line_count})
        return script, revision

    def mark_roles_confirmed(self, state: DramaWorkflowState, roles: list[dict[str, Any]]) -> None:
        """Persist the exact character-card choices used to generate the script."""
        validated = RoleDraftList.model_validate({"roles": roles}).model_dump()["roles"]
        revision = self.db.execute(
            select(AdaptationDraftRevisionPO)
            .where(
                AdaptationDraftRevisionPO.session_id == state["session_id"],
                AdaptationDraftRevisionPO.draft_type == "roles",
            )
            .order_by(AdaptationDraftRevisionPO.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        if revision:
            revision.payload_json = {"roles": validated}
            self.db.commit()

    def mark_script_confirmed(self, state: DramaWorkflowState, script: dict[str, Any]) -> None:
        session, run, _ = self._context(state["session_id"])
        validated = DramaScript.model_validate(script).model_dump()
        run.final_json = validated
        run.status = "script_ready"
        run.current_stage = "script_draft_ready"
        session.current_stage = "script_draft_ready"
        session.active_confirm_type = None
        session.pending_confirm_json = None
        self.db.commit()
        self._add_message(session.id, "assistant", "confirm", "剧本已确认，可以安全写入项目。", {"draft_revision": run.draft_revision})
        self.events.publish(session, "awaiting_confirmation", {"confirm_type": "commit", "draft_revision": run.draft_revision})

    def mark_cancelled(self, state: DramaWorkflowState) -> None:
        session = self._session(state["session_id"])
        session.status = "cancelled"
        session.current_stage = "cancelled"
        session.active_confirm_type = None
        session.pending_confirm_json = None
        self.db.commit()
        self._add_message(session.id, "assistant", "status", "本次改编会话已取消。")
        self.events.publish(session, "workflow_cancelled")

    def _invoke(self, session: ChatSessionPO, graph_input) -> dict[str, Any]:
        token = self._acquire_lease(session)
        config = {"configurable": {"thread_id": session.id}}
        try:
            with open_drama_checkpointer() as checkpointer:
                graph = build_drama_graph(self, checkpointer)
                graph.invoke(graph_input, config=config)
            return self.snapshot(session.id)
        except Exception as exc:
            logging.exception("对话式改编失败: session=%s stage=%s", session.id, session.current_stage)
            self._mark_failed(session.id, exc)
            raise
        finally:
            self._release_lease(session.id, token)

    def _mark_failed(self, session_id: str, exc: Exception) -> None:
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
        if session.adaptation_run_id:
            run = self.db.get(AdaptationRunPO, session.adaptation_run_id)
            if run:
                run.status = "failed"
                run.current_stage = "failed"
                run.error_message = message
        self.db.commit()
        self._add_message(session.id, "assistant", "error", message, {"error_code": code})
        self.events.publish(session, "workflow_failed", {"error_code": code, "message": message})

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
            id=f"msg_{uuid4().hex}", session_id=session_id, role=role, message_type=message_type,
            content=content, payload_json=payload or {}, client_request_id=client_request_id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def _save_revision(self, session_id: str, run_id: int, draft_type: str, payload: dict[str, Any], feedback: str | None) -> int:
        current = self.db.execute(
            select(func.max(AdaptationDraftRevisionPO.revision)).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == draft_type,
            )
        ).scalar_one_or_none() or 0
        revision = current + 1
        self.db.add(AdaptationDraftRevisionPO(
            session_id=session_id, run_id=run_id, draft_type=draft_type,
            revision=revision, payload_json=payload, feedback=feedback or None,
        ))
        self.db.commit()
        return revision

    def _latest_revision(self, session_id: str, draft_type: str):
        revision = self.db.execute(
            select(AdaptationDraftRevisionPO).where(
                AdaptationDraftRevisionPO.session_id == session_id,
                AdaptationDraftRevisionPO.draft_type == draft_type,
            ).order_by(AdaptationDraftRevisionPO.revision.desc()).limit(1)
        ).scalar_one_or_none()
        return revision.payload_json if revision else None

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
            "confirm_roles": "确认角色并生成剧本", "confirm_script": "确认剧本",
            "retry": "重试当前步骤", "cancel": "取消会话",
        }.get(action, action)
