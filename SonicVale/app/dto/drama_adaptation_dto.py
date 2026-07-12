from typing import Any, Optional

from pydantic import BaseModel, Field


class DramaAdaptationRequestDTO(BaseModel):
    project_id: int
    title: str = Field(default="未命名广播剧")
    chapter_title: Optional[str] = None
    source_text: str
    instruction: Optional[str] = None
    scene_count: int = Field(default=4, ge=1, le=24)
    adaptation_density: str = "balanced"
    commit_to_project: bool = True
    replace_chapter_lines: bool = True


class DramaAdaptationCommitRequestDTO(BaseModel):
    run_id: int
    chapter_title: Optional[str] = None
    replace_chapter_lines: bool = True


class DramaLineDTO(BaseModel):
    type: str = "dialogue"
    track: str = "voice"
    should_speak: bool = True
    speaker: str = "旁白"
    text: str
    emotion: Optional[str] = None
    strength: Optional[str] = None
    voice_profile: Optional[str] = None
    sound_prompt: Optional[str] = None
    production_note: Optional[str] = None


class DramaSceneDTO(BaseModel):
    title: str
    location: Optional[str] = None
    mood: Optional[str] = None
    lines: list[DramaLineDTO] = Field(default_factory=list)


class DramaScriptDTO(BaseModel):
    title: str
    logline: Optional[str] = None
    characters: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[DramaSceneDTO] = Field(default_factory=list)


class DramaAdaptationResponseDTO(BaseModel):
    run_id: int
    project_id: int
    chapter_id: Optional[int] = None
    status: str
    current_stage: str
    script: Optional[dict[str, Any]] = None
    message: str
