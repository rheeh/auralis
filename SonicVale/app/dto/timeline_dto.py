from pydantic import BaseModel, Field


class TimelineClipUpdateDTO(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=1)
    volume_db: float | None = Field(default=None, ge=-60, le=12)
    fade_in_ms: int | None = Field(default=None, ge=0)
    fade_out_ms: int | None = Field(default=None, ge=0)
    is_muted: bool | None = None
