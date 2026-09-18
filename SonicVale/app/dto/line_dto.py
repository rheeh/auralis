from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Optional, Literal

class LineTypeChangeDTO(BaseModel):
    chapter_id: int = Field(gt=0)
    track: Literal['voice', 'narration', 'sfx', 'bgm']
    role_id: Optional[int] = Field(default=None, gt=0)
    text_content: str = Field(min_length=1, max_length=10000)
    production_note: str = Field(default='', max_length=2000)

class LineInitDTO(BaseModel):
    role_name: Optional[str] = None
    text_content: str
    emotion_name: Optional[str] = None
    strength_name: Optional[str] = None


class LineOrderDTO(BaseModel):
    id: int
    line_order: int
class LineAudioProcessDTO(BaseModel):
    # 默认是1
    speed: Optional[float] = 1.0
    # 默认是1
    volume: Optional[float] = 1.0
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
#     静止时间
    silence_sec: Optional[float] = 0.0
    current_ms: Optional[int] = None

class LineAudioVariantDTO(LineAudioProcessDTO):
    label: Optional[str] = None
    region_action: Optional[str] = None

class LineAssetAttachDTO(BaseModel):
    source_path: str

class LineCreateDTO(BaseModel):
    chapter_id: int
    role_id:Optional[int] = None
    voice_id : Optional[int] = None
    line_order: Optional[int] = None
    id: Optional[int] = None
    text_content: Optional[str] = None
    line_type: Optional[str] = "dialogue"
    track: Optional[str] = "voice"
    should_speak: Optional[int] = 1
    scene_title: Optional[str] = None
    sound_prompt: Optional[str] = None
    sound_tags: Optional[list[str]] = None
    voice_profile: Optional[str] = None
    production_note: Optional[str] = None
    audio_events: Optional[list[dict[str, Any]]] = None
    audio_versions: Optional[list[dict[str, Any]]] = None
    active_audio_version_id: Optional[str] = None
    audio_variants: Optional[list[dict[str, Any]]] = None
    active_audio_variant_id: Optional[str] = None

    emotion_id: Optional[int] = None
    strength_id: Optional[int] = None

    audio_path : Optional[str] = None
    status : Optional[str] = None
    is_done : Optional[int] = 0
    subtitle_path : Optional[str] = None

class LineResponseDTO(BaseModel):
    chapter_id: int
    role_id:Optional[int] = None
    voice_id : Optional[int] = None
    line_order: Optional[int] = None
    id: Optional[int] = None
    text_content: Optional[str] = None
    line_type: Optional[str] = "dialogue"
    track: Optional[str] = "voice"
    should_speak: Optional[int] = 1
    scene_title: Optional[str] = None
    sound_prompt: Optional[str] = None
    sound_tags: Optional[list[str]] = None
    voice_profile: Optional[str] = None
    production_note: Optional[str] = None
    audio_events: Optional[list[dict[str, Any]]] = None
    audio_versions: Optional[list[dict[str, Any]]] = None
    active_audio_version_id: Optional[str] = None
    audio_variants: Optional[list[dict[str, Any]]] = None
    active_audio_variant_id: Optional[str] = None

    emotion_id: Optional[int] = None
    strength_id: Optional[int] = None

    audio_path : Optional[str] = None
    status : Optional[str] = None
    is_done: Optional[int] = 0
    subtitle_path : Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LineUpdateDTO(BaseModel):
    model_config = {"extra": "forbid"}
    text_content: str | None = Field(default=None, min_length=1, max_length=10000)
    role_id: int | None = Field(default=None, gt=0)
    voice_id: int | None = Field(default=None, gt=0)
    emotion_id: int | None = Field(default=None, gt=0)
    strength_id: int | None = Field(default=None, gt=0)
    production_note: str | None = Field(default=None, max_length=2000)
    scene_title: str | None = None
    voice_profile: str | None = None
    sound_prompt: str | None = None
    sound_tags: list[str] | None = None


class LinePublicCreateDTO(LineUpdateDTO):
    chapter_id: int = Field(gt=0)
    text_content: str = Field(min_length=1, max_length=10000)
    line_order: int | None = Field(default=None, gt=0)
    line_type: Literal['dialogue','narration','sfx','bgm'] = 'dialogue'
    track: Literal['voice','narration','sfx','bgm'] = 'voice'
    should_speak: Literal[0,1] = 1
