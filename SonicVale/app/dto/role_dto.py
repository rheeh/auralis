from datetime import datetime

from pydantic import BaseModel
from typing import Optional


class RoleCreateDTO(BaseModel):
    name: str
    project_id: int
    id: Optional[int] = None
    default_voice_id: Optional[int] = None
    role_importance: Optional[str] = "supporting"
    tts_route: Optional[str] = "auto"
    edge_voice: Optional[str] = None
    avatar_path: Optional[str] = None

class RoleResponseDTO(BaseModel):
    name: str
    project_id: int
    id: Optional[int] = None
    default_voice_id: Optional[int] = None
    role_importance: Optional[str] = "supporting"
    tts_route: Optional[str] = "auto"
    edge_voice: Optional[str] = None
    avatar_path: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
