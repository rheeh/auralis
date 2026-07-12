from __future__ import annotations

from typing import Any, Protocol

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.workflows.drama.state import DramaWorkflowState


class DramaNodeBackend(Protocol):
    def update_stage(self, state: DramaWorkflowState, stage: str, confirm_type: str | None = None) -> None: ...
    def parse_source(self, state: DramaWorkflowState) -> dict[str, Any]: ...
    def draft_roles(self, state: DramaWorkflowState) -> tuple[list[dict[str, Any]], int]: ...
    def draft_script(self, state: DramaWorkflowState) -> tuple[dict[str, Any], int]: ...
    def mark_script_confirmed(self, state: DramaWorkflowState, script: dict[str, Any]) -> None: ...
    def mark_cancelled(self, state: DramaWorkflowState) -> None: ...


def build_drama_graph(backend: DramaNodeBackend, checkpointer):
    builder = StateGraph(DramaWorkflowState)

    def receive_input(state: DramaWorkflowState):
        backend.update_stage(state, "created")
        return {"current_stage": "created", "iteration_count": state.get("iteration_count", 0)}

    def parse_source_text(state: DramaWorkflowState):
        backend.update_stage(state, "parsing")
        parsed = backend.parse_source(state)
        return {"parsed_source": parsed, "current_stage": "parsing", "error_code": None, "error_message": None}

    def draft_roles(state: DramaWorkflowState):
        roles, revision = backend.draft_roles(state)
        pending = {"type": "roles", "revision": revision, "actions": ["confirm_roles", "revise_roles", "cancel"]}
        backend.update_stage(state, "awaiting_role_confirmation", "roles")
        return {
            "role_drafts": roles,
            "role_revision": revision,
            "current_stage": "awaiting_role_confirmation",
            "pending_confirm": pending,
        }

    def role_confirmation(state: DramaWorkflowState):
        action = interrupt({
            "type": "roles",
            "revision": state.get("role_revision", 1),
            "roles": state.get("role_drafts", []),
            "actions": ["confirm_roles", "revise_roles", "cancel"],
        })
        return {"user_action": action, "user_feedback": action.get("feedback", "")}

    def route_role_action(state: DramaWorkflowState):
        return state.get("user_action", {}).get("action", "revise_roles")

    def apply_role_feedback(state: DramaWorkflowState):
        action = state.get("user_action", {})
        return {
            "user_feedback": action.get("feedback", ""),
            "iteration_count": state.get("iteration_count", 0) + 1,
            "user_action": None,
        }

    def confirm_roles(state: DramaWorkflowState):
        action = state.get("user_action", {})
        submitted = action.get("payload", {}).get("roles") or state.get("role_drafts", [])
        confirmed = [role for role in submitted if role.get("selected", True)]
        backend.mark_roles_confirmed(state, confirmed)
        return {"confirmed_roles": confirmed, "pending_confirm": None, "user_action": None, "user_feedback": ""}

    def generate_script_draft(state: DramaWorkflowState):
        backend.update_stage(state, "generating_script")
        script, revision = backend.draft_script(state)
        pending = {"type": "script", "revision": revision, "actions": ["confirm_script", "revise_script", "cancel"]}
        backend.update_stage(state, "awaiting_script_confirmation", "script")
        return {
            "script_draft": script,
            "script_revision": revision,
            "current_stage": "awaiting_script_confirmation",
            "pending_confirm": pending,
        }

    def script_confirmation(state: DramaWorkflowState):
        action = interrupt({
            "type": "script",
            "revision": state.get("script_revision", 1),
            "script": state.get("script_draft"),
            "actions": ["confirm_script", "revise_script", "cancel"],
        })
        return {"user_action": action, "user_feedback": action.get("feedback", "")}

    def route_script_action(state: DramaWorkflowState):
        return state.get("user_action", {}).get("action", "revise_script")

    def apply_script_feedback(state: DramaWorkflowState):
        action = state.get("user_action", {})
        return {
            "user_feedback": action.get("feedback", ""),
            "iteration_count": state.get("iteration_count", 0) + 1,
            "user_action": None,
        }

    def confirm_script(state: DramaWorkflowState):
        action = state.get("user_action", {})
        script = action.get("payload", {}).get("script") or state.get("script_draft") or {}
        backend.mark_script_confirmed(state, script)
        return {
            "confirmed_script": script,
            "current_stage": "script_draft_ready",
            "pending_confirm": None,
            "user_action": None,
            "user_feedback": "",
        }

    def cancel(state: DramaWorkflowState):
        backend.mark_cancelled(state)
        return {"current_stage": "cancelled", "pending_confirm": None, "user_action": None}

    builder.add_node("receive_input", receive_input)
    builder.add_node("parse_source_text", parse_source_text)
    builder.add_node("draft_roles", draft_roles)
    builder.add_node("role_confirmation", role_confirmation)
    builder.add_node("apply_role_feedback", apply_role_feedback)
    builder.add_node("confirm_roles", confirm_roles)
    builder.add_node("generate_script_draft", generate_script_draft)
    builder.add_node("script_confirmation", script_confirmation)
    builder.add_node("apply_script_feedback", apply_script_feedback)
    builder.add_node("confirm_script", confirm_script)
    builder.add_node("cancel", cancel)

    builder.add_edge(START, "receive_input")
    builder.add_edge("receive_input", "parse_source_text")
    builder.add_edge("parse_source_text", "draft_roles")
    builder.add_edge("draft_roles", "role_confirmation")
    builder.add_conditional_edges("role_confirmation", route_role_action, {
        "confirm_roles": "confirm_roles", "revise_roles": "apply_role_feedback", "cancel": "cancel",
    })
    builder.add_edge("apply_role_feedback", "draft_roles")
    builder.add_edge("confirm_roles", "generate_script_draft")
    builder.add_edge("generate_script_draft", "script_confirmation")
    builder.add_conditional_edges("script_confirmation", route_script_action, {
        "confirm_script": "confirm_script", "revise_script": "apply_script_feedback", "cancel": "cancel",
    })
    builder.add_edge("apply_script_feedback", "generate_script_draft")
    builder.add_edge("confirm_script", END)
    builder.add_edge("cancel", END)
    return builder.compile(checkpointer=checkpointer)
