from __future__ import annotations

from typing import Literal


SourceType = Literal["novel", "knowledge_article"]
AdaptationMode = Literal["drama", "auto", "audio_lesson", "knowledge_drama"]
ArticleCategory = Literal["auto", "science", "technology", "business", "management"]
LearningGoal = Literal["quick_understanding", "concept_mastery", "practical_application", "memory_reinforcement"]
VerificationMode = Literal["source_only", "external_verification"]

NOVEL_SOURCE_TYPE = "novel"
KNOWLEDGE_ARTICLE_SOURCE_TYPE = "knowledge_article"


def default_adaptation_mode(source_type: SourceType) -> str:
    return "drama" if source_type == NOVEL_SOURCE_TYPE else "auto"
