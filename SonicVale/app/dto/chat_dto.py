from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceDocumentCreateDTO(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class ChatSessionCreateDTO(BaseModel):
    project_id: int
    chapter_id: int | None = None
    source_text: str | None = None
    source_document_id: int | None = None
    instruction: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.source_text and self.source_text.strip()) == bool(self.source_document_id):
            raise ValueError("source_text 和 source_document_id 必须且只能提供一个")
        return self


class ChatMessageCreateDTO(BaseModel):
    message: str = Field(min_length=1)
    client_request_id: str = Field(min_length=1, max_length=128)


class ChatConfirmDTO(BaseModel):
    confirm_type: Literal["roles", "script"]
    action: Literal["confirm_roles", "revise_roles", "confirm_script", "revise_script"]
    feedback: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str = Field(min_length=1, max_length=128)


class ChatCommitDTO(BaseModel):
    chapter_title: str | None = None
    replace_chapter_lines: bool = True
    client_request_id: str = Field(min_length=1, max_length=128)


class AudioReviewDTO(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=1000)


class LineAudioRegenerateDTO(BaseModel):
    prompt: str = Field(default="", max_length=500)
