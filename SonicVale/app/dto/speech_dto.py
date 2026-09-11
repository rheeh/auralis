import re
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PronunciationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    term: str = Field(min_length=1, max_length=80)
    pronunciation: str = Field(default="", max_length=240)
    spoken_as: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def validate_entry(self):
        if not self.pronunciation and not self.spoken_as:
            raise ValueError("请填写拼音或替代读法")
        if self.pronunciation and not re.fullmatch(r"[a-zA-ZüÜvV:]+[1-5]?(?:\s+[a-zA-ZüÜvV:]+[1-5]?)*", self.pronunciation):
            raise ValueError("拼音请使用空格分隔的音节，例如 chong2 qing4")
        if re.search(r"[<>\[\]【】()（）]", self.term + self.spoken_as):
            raise ValueError("词条与替代读法不能包含标记或括号指令")
        return self


class ProjectSpeechSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    story_background: str = Field(default="", max_length=1200)
    delivery_style: str = Field(default="自然交谈，声线稳定，情绪随剧情逐步变化。", max_length=400)
    continuity_enabled: bool = True
    pronunciation_entries: list[PronunciationEntry] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_terms(self):
        terms = [entry.term for entry in self.pronunciation_entries]
        if len(set(terms)) != len(terms):
            raise ValueError("发音词条不能重复")
        return self
