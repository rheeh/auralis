from typing import Literal

from pydantic import BaseModel, Field


class SoundLibraryImportDTO(BaseModel):
    source_path: str
    name: str | None = None
    category: str = "foley"
    tags: list[str] = Field(default_factory=list)


class SoundLibraryInsertDTO(BaseModel):
    chapter_id: int = Field(gt=0)
    anchor_line_id: int | None = Field(default=None, gt=0)
    placement: Literal["before", "with", "after", "scene_start"] = "with"
    offset_ms: int = Field(default=0, ge=-60000, le=60000)
    duration_ms: int | None = Field(default=None, ge=1)
    volume_db: float = Field(default=-12, ge=-60, le=12)
    fade_in_ms: int = Field(default=0, ge=0)
    fade_out_ms: int = Field(default=0, ge=0)
