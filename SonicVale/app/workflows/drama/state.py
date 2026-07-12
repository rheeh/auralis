from __future__ import annotations

from typing import Any, TypedDict


class DramaWorkflowState(TypedDict, total=False):
    session_id: str
    project_id: int
    chapter_id: int | None
    source_document_id: int | None
    source_text_ref: str | None
    user_instruction: str | None
    current_stage: str
    conversation_summary: str | None
    parsed_source: dict[str, Any] | None
    role_drafts: list[dict[str, Any]]
    confirmed_roles: list[dict[str, Any]]
    role_revision: int
    script_draft: dict[str, Any] | None
    confirmed_script: dict[str, Any] | None
    script_revision: int
    pending_confirm: dict[str, Any] | None
    user_action: dict[str, Any] | None
    user_feedback: str | None
    iteration_count: int
    last_event_id: str | None
    error_code: str | None
    error_message: str | None
