from __future__ import annotations
from app.core.sound_tags import script_sound_tags, normalize_tags

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.workflows.drama.performance import ScenePerformancePlan, LinePerformanceCue


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
    soundTags: list[str] = Field(default_factory=list)
    productionNote: str | None = None
    audioEvents: list[AudioEvent] = Field(default_factory=list)
    performanceCue: LinePerformanceCue | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_clean_script_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "role_name": "speaker", "text_content": "text", "emotion_name": "emotion",
            "strength_name": "strength", "production_note": "productionNote",
            "audio_events": "audioEvents", "sound_prompt": "soundPrompt", "sound_tags": "soundTags",
        }
        for source, target in aliases.items():
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]
        if "soundTags" in normalized:
            normalized["soundTags"] = normalize_tags(normalized["soundTags"])
        # Some compatible models use the audio-event label "amb" for a whole
        # environmental row. Only normalize an explicitly non-spoken row with
        # a compatible sound track; never reinterpret possible dialogue or
        # silently discard a timing-only "break" row.
        if (
            normalized.get("type") == "amb"
            and normalized.get("shouldSpeak") is False
            and normalized.get("track") in {None, "amb", "sfx"}
        ):
            normalized["type"] = "sfx"
            normalized["track"] = "sfx"
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
            self.soundTags = script_sound_tags(self.soundTags, prompt)
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
                    # Actor delivery belongs to the same voice, not a stock effect.
                    performance = re.search(r"笑|叹气|叹息|抽泣|哽咽|喘息|吸气|呼气|停顿|重音|语速|语气|压低声音", content)
                    external = re.search(r"人群|观众|众人|背景|远处|电视|录音|门外", content)
                    if performance and not external:
                        self.productionNote = "；".join(filter(None, [self.productionNote, content]))
                    else:
                        self.audioEvents.append(AudioEvent(timing="台词中", type="sfx", content=content, volume_db="-18dB"))
            self.text = re.sub(bracket_pattern, "", self.text)
            self.text = re.sub(r"[ \t]+", " ", self.text).strip()
            if not self.text and bracket_notes and not self.audioEvents and re.search(r'笑', self.productionNote or ''):
                self.text = '哈哈。' if re.search(r'大笑|哈哈', self.productionNote) else '呵。'
            if not self.text:
                raise ValueError("可朗读台词不能只包含括号提示或音效标记")
            self.emotion = (self.emotion or "平静").strip() or "平静"
            self.strength = (self.strength or "微弱").strip() or "微弱"
            if self.type == "narration":
                self.speaker = "旁白"
                self.emotion = "平静"
                # Explicit direction may be retained; a missing label stays subtle.
                self.strength = self.strength or "微弱"
        return self


class ScriptScene(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    location: str = ""
    mood: str = ""
    lines: list[ScriptLine] = Field(min_length=1)
    performancePlan: ScenePerformancePlan | None = None

    @model_validator(mode="after")
    def validate_performance_references(self):
        if self.performancePlan is None:
            if any(line.performanceCue for line in self.lines):
                raise ValueError("逐句表演提示必须属于场景表演设计")
            return self
        beats = {beat.id: index for index, beat in enumerate(self.performancePlan.beats)}
        speakers = {item.speaker for item in self.performancePlan.characters}
        previous_beat = -1
        for index, line in enumerate(self.lines, 1):
            cue = line.performanceCue
            if not line.shouldSpeak:
                if cue is not None:
                    raise ValueError("音效和音乐不能绑定人物表演提示")
                continue
            if cue is None or cue.beatId not in beats:
                raise ValueError("每句人物声和旁白必须绑定有效的表演节拍")
            if line.speaker not in speakers:
                raise ValueError("表演设计缺少当前说话人的意图与基调")
            if beats[cue.beatId] < previous_beat:
                raise ValueError("台词表演节拍不能逆序，重复动作应建立新的节拍")
            previous_beat = beats[cue.beatId]
            if cue.respondsTo is not None and (cue.respondsTo >= index or not self.lines[cue.respondsTo - 1].shouldSpeak):
                raise ValueError("接话对象必须是本场已经发生的可朗读台词")
        return self


class DramaScript(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    logline: str = ""
    characters: list[dict[str, Any]] = Field(min_length=1)
    scenes: list[ScriptScene] = Field(min_length=1)


class DirectedScriptScene(ScriptScene):
    # Required for new LLM generations; historical scripts remain readable.
    performancePlan: ScenePerformancePlan


class DirectedDramaScript(DramaScript):
    scenes: list[DirectedScriptScene] = Field(min_length=1)


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
