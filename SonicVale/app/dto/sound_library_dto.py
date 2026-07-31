from pydantic import BaseModel, Field


class SoundLibraryImportDTO(BaseModel):
    source_path: str
    name: str | None = None
    category: str = "foley"
    tags: list[str] = Field(default_factory=list)
