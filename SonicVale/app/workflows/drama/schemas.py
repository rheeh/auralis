from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WorkflowStage = Literal[
    "created", "parsing", "role_draft_ready", "awaiting_role_confirmation",
    "generating_script", "reviewing_script", "script_draft_ready", "awaiting_script_confirmation",
    "committing", "completed", "failed", "cancelled",
]


class SourceCharacter(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=100)
    role: str = ""
    traits: list[str] = Field(default_factory=list)
    motivation: str = ""
    voiceClues: str = ""


class SourceScenePlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    location: str = ""
    mood: str = ""
    plotBeats: list[str] = Field(default_factory=list)
    likelySfx: list[str] = Field(default_factory=list)
    likelyBgm: str = ""


class SourceContentMapEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    category: str
    audioStrategy: Literal["dialogue", "sfx", "bgm", "silence", "narration", "delete"]
    keepAsNarration: bool = False
    reason: str = ""


class SourceAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = "未命名作品"
    logline: str = ""
    genre: str = ""
    narratorPointOfView: str = ""
    characters: list[SourceCharacter] = Field(min_length=1)
    scenePlan: list[SourceScenePlan] = Field(min_length=1)
    contentMap: list[SourceContentMapEntry] = Field(min_length=1)


class RoleDraft(BaseModel):
    model_config = ConfigDict(extra="allow")

    draft_id: str
    name: str = Field(min_length=1, max_length=100)
    identity: str = ""
    personality: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    speech_style: str = ""
    voice_type: str = ""
    selected: bool = True
    default_voice_id: int | None = None
    avatar_path: str | None = None


class RoleDraftList(BaseModel):
    roles: list[RoleDraft] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_role_names(self):
        names = [role.name.strip().casefold() for role in self.roles]
        if len(names) != len(set(names)):
            raise ValueError("角色名不能重复")
        return self


class AudioEvent(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    timing: str = "台词中"
    type: Literal["sfx", "amb", "bgm", "reverb", "break"] = "sfx"
    content: str = Field(min_length=1)
    volume_db: str = "-18dB"


class ScriptLine(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["dialogue", "narration", "sfx", "bgm"] = "dialogue"
    track: Literal["voice", "narration", "sfx", "bgm"] = "voice"
    shouldSpeak: bool = True
    speaker: str = "旁白"
    text: str = ""
    emotion: str | None = None
    strength: str | None = None
    voiceProfile: str | None = None
    soundPrompt: str | None = None
    productionNote: str | None = None
    audioEvents: list[AudioEvent] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_clean_script_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "role_name": "speaker", "text_content": "text", "emotion_name": "emotion",
            "strength_name": "strength", "production_note": "productionNote",
            "audio_events": "audioEvents", "sound_prompt": "soundPrompt",
        }
        for source, target in aliases.items():
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]
        return normalized

    @model_validator(mode="after")
    def normalize_speakability(self):
        self.shouldSpeak = self.type in {"dialogue", "narration"}
        if self.type == "narration":
            self.track = "narration"
            self.speaker = self.speaker or "旁白"
        elif self.type in {"sfx", "bgm"}:
            self.track = self.type
            self.speaker = "音效" if self.type == "sfx" else "BGM"
            prompt = (self.soundPrompt or self.text or self.productionNote or "").strip()
            self.soundPrompt = prompt or None
            if prompt and not self.text.strip():
                self.text = prompt
        elif self.track not in {"voice", "narration"}:
            self.track = "voice"
        if self.shouldSpeak:
            bracket_pattern = r"(?:\([^()]*\)|（[^（）]*）|\[[^\[\]]*\]|【[^【】]*】)"
            bracket_notes = re.findall(bracket_pattern, self.text)
            for raw_note in bracket_notes:
                content = raw_note.strip("()（）[]【】 ")
                if content:
                    self.audioEvents.append(AudioEvent(timing="台词中", type="sfx", content=content, volume_db="-18dB"))
            self.text = re.sub(bracket_pattern, "", self.text)
            self.text = re.sub(r"[ \t]+", "", self.text).strip()
            if not self.text:
                raise ValueError("可朗读台词不能只包含括号提示或音效标记")
            self.emotion = (self.emotion or "平静").strip() or "平静"
            self.strength = (self.strength or "中等").strip() or "中等"
            if self.type == "narration":
                self.speaker = "旁白"
                self.emotion = "平静"
                self.strength = "中等"
        return self


class ScriptScene(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    location: str = ""
    mood: str = ""
    lines: list[ScriptLine] = Field(min_length=1)


class DramaScript(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    logline: str = ""
    characters: list[dict[str, Any]] = Field(min_length=1)
    scenes: list[ScriptScene] = Field(min_length=1)


class ScriptReviewIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    severity: Literal["error", "warning", "suggestion"] = "warning"
    category: str = "声音表达"
    scene_title: str = ""
    line_index: int | None = None
    evidence: str = ""
    suggestion: str = ""


class ScriptReviewReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: bool
    score: int = Field(default=80, ge=0, le=100)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[ScriptReviewIssue] = Field(default_factory=list)


class WorkflowAction(BaseModel):
    action: Literal[
        "confirm_roles", "revise_roles", "confirm_script", "revise_script",
        "retry", "cancel", "commit",
    ]
    feedback: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str
