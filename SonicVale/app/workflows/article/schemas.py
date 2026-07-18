from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ArticleWorkflowStage = Literal[
    "created", "importing_source", "source_ready", "analyzing_article",
    "outline_ready", "awaiting_outline_confirmation", "designing_learning_plan", "learning_plan_ready",
    "generating_knowledge_script", "reviewing_knowledge_script",
    "awaiting_script_confirmation", "knowledge_script_ready", "committed", "generating_audio",
    "audio_ready", "completed", "failed", "cancelled",
]


class ArticleSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    source_location: str = ""


class KnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    one_sentence_summary: str = ""
    explanation: str = ""
    importance: Literal["required", "recommended", "optional"] = "recommended"
    source_excerpt: str = Field(min_length=1)
    source_location: str = ""
    example: str = ""
    common_misunderstanding: str = ""
    audio_order: int = Field(default=1, ge=1)
    content_origin: Literal[
        "fact_from_source", "opinion_from_source", "example_from_source",
        "ai_explanation", "external_verified_fact", "uncertain_claim",
    ] = "fact_from_source"
    is_ai_supplement: bool = False


class ArticleAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    category: str = "auto"
    audience: str = ""
    estimated_reading_level: str = ""
    sections: list[ArticleSection] = Field(min_length=1)
    key_points: list[KnowledgePoint] = Field(min_length=1)
    terms: list[dict] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_spans: list[dict] = Field(default_factory=list)
    recommended_format: Literal["audio_lesson", "dialogue_lesson", "knowledge_drama"] = "audio_lesson"
    recommended_duration: int = Field(default=10, ge=5, le=15)

    @model_validator(mode="after")
    def unique_knowledge_point_ids(self):
        ids = [item.id for item in self.key_points]
        if len(ids) != len(set(ids)):
            raise ValueError("知识点 id 不能重复")
        return self


class LearningPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    learning_goal: str
    target_duration_minutes: int = Field(ge=5, le=15)
    adaptation_mode: str
    recommended_reason: str = ""
    ordered_knowledge_point_ids: list[str] = Field(min_length=1)
    review_moments: list[dict] = Field(default_factory=list)


class KnowledgeScriptLine(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["dialogue", "narration", "sfx", "bgm"] = "dialogue"
    track: Literal["voice", "narration", "sfx", "bgm"] = "voice"
    should_speak: bool = True
    speaker: str = "讲解者"
    text: str = ""
    emotion: str | None = None
    strength: str | None = None
    voice_profile: str | None = None
    production_note: str | None = None
    sound_prompt: str | None = None
    knowledge_point_ids: list[str] = Field(default_factory=list)
    content_origin: Literal[
        "fact_from_source", "opinion_from_source", "example_from_source",
        "ai_explanation", "external_verified_fact", "uncertain_claim",
    ] = "fact_from_source"

    @model_validator(mode="after")
    def normalize_line(self):
        self.should_speak = self.type in {"dialogue", "narration"}
        if self.type == "narration":
            self.track = "narration"
        elif self.type in {"sfx", "bgm"}:
            self.track = self.type
            self.should_speak = False
        elif self.track not in {"voice", "narration"}:
            self.track = "voice"
        if self.should_speak and not self.text.strip():
            raise ValueError("可朗读知识台词不能为空")
        return self


class KnowledgeScriptSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    segment_type: Literal["opening", "knowledge_point", "case", "summary", "review"]
    knowledge_point_ids: list[str] = Field(default_factory=list)
    lines: list[KnowledgeScriptLine] = Field(min_length=1)


class ReviewQuestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    knowledge_point_id: str = Field(min_length=1)
    source_excerpt: str = Field(min_length=1)


class KnowledgeScript(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(min_length=1)
    adaptation_mode: Literal["audio_lesson", "dialogue_lesson", "knowledge_drama"]
    roles: list[dict] = Field(min_length=1, max_length=3)
    segments: list[KnowledgeScriptSegment] = Field(min_length=1)
    review_questions: list[ReviewQuestion] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def validate_knowledge_links(self):
        if not any(segment.knowledge_point_ids for segment in self.segments):
            raise ValueError("知识脚本必须关联至少一个知识点")
        return self


class KnowledgeReviewReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: bool
    accuracy_score: int = Field(default=80, ge=0, le=100)
    learning_quality_score: int = Field(default=80, ge=0, le=100)
    audio_quality_score: int = Field(default=80, ge=0, le=100)
    summary: str = ""
    issues: list[dict] = Field(default_factory=list)
    coverage: list[dict] = Field(default_factory=list)
    unmarked_supplements: list[str] = Field(default_factory=list)
