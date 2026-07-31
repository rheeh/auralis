
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional



@dataclass
class LineEntity:
    """业务实体：台词"""
    chapter_id: int
    id: Optional[int] = None
    role_id : Optional[ int] = None
    voice_id : Optional[int] = None
    line_order : Optional[int] = None
    text_content : Optional[str] = None
    line_type : Optional[str] = "dialogue"
    track : Optional[str] = "voice"
    should_speak : Optional[int] = 1
    scene_title : Optional[str] = None
    sound_prompt : Optional[str] = None
    voice_profile : Optional[str] = None
    production_note : Optional[str] = None
    audio_events: Optional[list[dict[str, Any]]] = None
    audio_versions: Optional[list[dict[str, Any]]] = None
    active_audio_version_id: Optional[str] = None
    audio_variants: Optional[list[dict[str, Any]]] = None
    active_audio_variant_id: Optional[str] = None

    emotion_id : Optional[int] = None
    strength_id : Optional[int] = None

    audio_path : Optional[str] = None
    subtitle_path : Optional[str] = None
    status : Optional[str] = None
    # 是否完成
    is_done : Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
