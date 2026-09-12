"""Scene direction is generated with the script, not once per TTS request."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CharacterPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    speaker: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=180)
    relationship: str = Field(default="", max_length=180)
    baseline: str = Field(min_length=1, max_length=180)


class PerformanceBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    purpose: str = Field(min_length=1, max_length=180)
    delivery: str = Field(min_length=1, max_length=180)


class ScenePerformancePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    purpose: str = Field(min_length=1, max_length=240)
    baseline: str = Field(min_length=1, max_length=180)
    pace: str = Field(min_length=1, max_length=180)
    characters: list[CharacterPerformance] = Field(default_factory=list, max_length=40)
    beats: list[PerformanceBeat] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def unique_references(self):
        for values in ([item.speaker for item in self.characters], [item.id for item in self.beats]):
            if len(values) != len(set(values)):
                raise ValueError("场景表演设计的人物和节拍标识不能重复")
        return self


class LinePerformanceCue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    beatId: str = Field(min_length=1, max_length=32)
    intent: str = Field(min_length=1, max_length=180)
    delivery: str = Field(default="", max_length=180)
    # One-based index into scene.lines, including sound rows. Only earlier speech.
    respondsTo: int | None = Field(default=None, ge=1)
    turningPoint: bool = False
    evidence: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def grounded_turn(self):
        if self.turningPoint and not self.evidence:
            raise ValueError("情绪转折必须附原文或用户要求中的直接依据")
        return self
