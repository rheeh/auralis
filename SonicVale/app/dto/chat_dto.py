from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.workflows.content_types import (
    AdaptationMode,
    ArticleCategory,
    LearningGoal,
    SourceType,
    VerificationMode,
    default_adaptation_mode,
)


class SourceDocumentCreateDTO(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class ArticleSourcePreviewDTO(BaseModel):
    project_id: int
    input_method: Literal["url", "paste"]
    source_url: str | None = Field(default=None, max_length=2000)
    source_text: str | None = None

    @model_validator(mode="after")
    def validate_input(self):
        if self.input_method == "url":
            if not self.source_url or not self.source_url.strip():
                raise ValueError("URL 导入必须提供 source_url")
            if self.source_text and self.source_text.strip():
                raise ValueError("URL 预览不能同时提供 source_text")
        else:
            if not self.source_text or not self.source_text.strip():
                raise ValueError("粘贴导入必须提供 source_text")
            if self.source_url and self.source_url.strip():
                raise ValueError("粘贴预览不能同时提供 source_url")
        return self


class ArticleSourceImportDTO(BaseModel):
    project_id: int
    session_id: str | None = Field(default=None, max_length=64)
    input_method: Literal["url", "paste"]
    source_url: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=255)
    account_name: str | None = Field(default=None, max_length=255)
    published_at: datetime | None = None
    source_text: str = Field(min_length=1)
    raw_content: str | None = None
    rights_confirmed: bool = False


class ArticleSourceNormalizeDTO(BaseModel):
    source_text: str | None = None


class ArticleOutlineActionDTO(BaseModel):
    feedback: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str = Field(min_length=1, max_length=128)


class ReviewQuestionAnswerDTO(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)


class ChatSessionCreateDTO(BaseModel):
    project_id: int
    chapter_id: int | None = None
    source_type: SourceType = "novel"
    adaptation_mode: AdaptationMode | None = None
    article_category: ArticleCategory | None = None
    learning_goal: LearningGoal | None = None
    target_duration_minutes: int | None = Field(default=None, ge=5, le=15)
    verification_mode: VerificationMode | None = None
    source_text: str | None = None
    source_document_id: int | None = None
    article_source_id: int | None = None
    instruction: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self):
        source_count = sum((
            bool(self.source_text and self.source_text.strip()),
            bool(self.source_document_id),
            bool(self.article_source_id),
        ))
        if source_count != 1:
            raise ValueError("source_text、source_document_id 和 article_source_id 必须且只能提供一个")
        if self.source_type == "novel" and self.article_source_id:
            raise ValueError("小说会话不能使用 article_source_id")
        if self.source_type == "knowledge_article" and self.source_document_id:
            raise ValueError("知识文章会话不能使用小说 source_document_id")
        if self.source_type == "novel":
            if self.adaptation_mode not in {None, "drama"}:
                raise ValueError("小说广播剧仅支持 drama 改编模式")
            self.adaptation_mode = "drama"
            self.article_category = None
            self.learning_goal = None
            self.target_duration_minutes = None
            self.verification_mode = None
        else:
            if self.adaptation_mode == "drama":
                raise ValueError("知识文章不能使用小说 drama 改编模式")
            self.adaptation_mode = self.adaptation_mode or default_adaptation_mode(self.source_type)
            self.article_category = self.article_category or "auto"
            self.learning_goal = self.learning_goal or "quick_understanding"
            self.target_duration_minutes = self.target_duration_minutes or 10
            self.verification_mode = self.verification_mode or "source_only"
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
