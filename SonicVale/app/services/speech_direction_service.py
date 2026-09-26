from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.tts_capabilities import cosyvoice_instruction_mode, http_instruction_field
from app.core.tts_engine import ConfigurableCloudTTSEngine, TTSEngine
from app.core.tts_guidance import emotion_text_to_vector, STRENGTH_NAMES, affirmative_guidance, build_voice_instruction, edge_prosody
from app.dto.speech_dto import ProjectSpeechSettings
from app.models.po import (AdaptationRunPO, ChapterPO, EmotionPO, LinePO, ProjectPO,
                           ProjectSpeechProfilePO, RolePO, StrengthPO, VoicePO)
from app.services.production_configuration import effective_provider_id
from app.models.po import TTSProviderPO
from app.services.scene_performance_service import resolve_scene_performance
from app.core.speech_context_budget import compile_context_instruction


POLICY_VERSION = "speech-context-2026-09-26-v3"


def clean_spoken_text(text):
    text = re.sub(r"(?:\([^()]*\)|（[^（）]*）|\[[^\[\]]*\]|【[^【】]*】)", "", str(text or ""))
    return re.sub(r"[ \t]+", " ", text).strip()


def is_spoken(line):
    return line.should_speak != 0 and line.track not in {"sfx", "bgm"} and line.line_type not in {"sfx", "bgm"}


def permits_emotion_jump(note):
    return any(word in affirmative_guidance(note or "") for word in
               ("情绪转折", "情绪突变", "爆发", "崩溃", "尖叫", "大喊", "哭喊", "突然大笑"))


class SpeechDirectionService:
    """Build repeatable, inspectable direction without an extra model call."""

    def __init__(self, db):
        self.db = db

    def project(self, project_id):
        project = self.db.get(ProjectPO, project_id)
        if not project:
            raise ValueError("项目不存在")
        return project

    def settings(self, project_id):
        self.project(project_id)
        row = self.db.get(ProjectSpeechProfilePO, project_id)
        return {**ProjectSpeechSettings.model_validate(row.settings if row else {}).model_dump(),
                "revision": row.revision if row else 0}

    def save_settings(self, project_id, dto):
        self.project(project_id)
        row = self.db.get(ProjectSpeechProfilePO, project_id)
        if row is None:
            row = ProjectSpeechProfilePO(project_id=project_id, revision=0)
            self.db.add(row)
        if row.settings == dto.model_dump():
            return self.settings(project_id)
        row.settings = dto.model_dump()
        row.revision += 1
        row.updated_at = datetime.now(timezone.utc)
        from app.services.timeline_service import TimelineService
        for line in self.db.scalars(select(LinePO).join(ChapterPO,ChapterPO.id==LinePO.chapter_id).where(ChapterPO.project_id==project_id)):
            if is_spoken(line):
                line.status,line.is_done='pending',0
                TimelineService.invalidate_line(self.db,line.id,'配音设定已变化',commit=False)
        self.db.commit()
        return self.settings(project_id)

    def line(self, project_id, line_id):
        self.project(project_id)
        line = self.db.get(LinePO, line_id)
        chapter = self.db.get(ChapterPO, line.chapter_id) if line else None
        if not chapter or chapter.project_id != project_id:
            raise ValueError("台词不属于此项目")
        return line, chapter

    def prepare(self, project_id, line_id, queued_line=None):
        from app.services.speech import routing as speech_routing

        saved_line, chapter = self.line(project_id, line_id)
        line = queued_line or saved_line
        if line.chapter_id != chapter.id or not is_spoken(line):
            raise ValueError("只有本章人物声和旁白可以生成配音")
        project = self.project(project_id)
        settings = self.settings(project_id)
        role = self.db.get(RolePO, line.role_id) if line.role_id else None
        if role and role.project_id != project_id:
            raise ValueError("角色不属于此项目")
        voice = self.db.get(VoicePO, role.default_voice_id) if role and role.default_voice_id else None
        provider_id = effective_provider_id(project, voice)
        provider = self.db.get(TTSProviderPO, provider_id) if provider_id else None
        if not provider or provider.status == 0:
            raise ValueError("请为角色选择已启用的配音模型")
        params = copy.deepcopy(ConfigurableCloudTTSEngine._parse_params(provider.custom_params))
        model = (provider.model or "").lower()
        voice_name = speech_routing.resolve_cosyvoice_voice(voice) or (voice.name if voice else None)
        route = speech_routing.resolve_tts_route(role, line.line_type, line.track)
        if provider.provider_type == "edge":
            route = "edge"
        elif speech_routing.resolve_cosyvoice_voice(voice):
            route = "cloud"
        emotions = {r.id: r.name for r in self.db.scalars(select(EmotionPO))}
        strengths = {r.id: r.name for r in self.db.scalars(select(StrengthPO))}
        emotion = emotions.get(line.emotion_id, "平静")
        strength = strengths.get(line.strength_id, "微弱")
        # Resolve routing with the same inputs as the production service.
        if provider.provider_type != "edge" and not speech_routing.resolve_cosyvoice_voice(voice):
            route = speech_routing.resolve_tts_route(role, line.line_type, line.track, emotion)
        mode = ("mapped" if route == "edge" else
                cosyvoice_instruction_mode(model, params, voice_name) if model.startswith("cosyvoice") else
                "native" if http_instruction_field(model, params) or "{{instruction}}" in json.dumps(params.get("payload") or params.get("body") or {}) else "none")
        rows = list(self.db.scalars(select(LinePO).where(LinePO.chapter_id == chapter.id).order_by(LinePO.line_order, LinePO.id)))
        position = next(i for i, item in enumerate(rows) if item.id == line_id)
        rows[position] = line  # preserve queued input, even if the editor has changed
        scene = line.scene_title or ""
        roles = {item.id: item.name for item in self.db.scalars(select(RolePO).where(RolePO.project_id == project_id))}
        start, end, performance, planned_cues = resolve_scene_performance(chapter, rows, position, roles)
        block = rows[start:end]
        previous = [item for item in rows[start:position] if is_spoken(item)][-2:]
        following = [item for item in rows[position + 1:end] if is_spoken(item)][:1]
        same_role = [item for item in rows[start:position] if is_spoken(item) and item.role_id == line.role_id]
        effective_strength = strength
        if settings["continuity_enabled"]:
            level = 1  # a stable dialogue baseline; never borrow another speaker's intensity
            for item in block:
                if not is_spoken(item) or item.role_id != line.role_id:
                    continue
                # Cap unexplained rises; never amplify a deliberately quiet line.
                selected = strengths.get(item.strength_id, "微弱")
                target = STRENGTH_NAMES.index(selected) if selected in STRENGTH_NAMES else 0
                # A reviewed, current scene plan uses its grounded turning points.
                # An edited/legacy scene falls back to explicit per-line direction.
                jump = (bool(planned_cues.get(str(item.id), {}).get("turning_point_verified"))
                        if performance["status"] == "current" else permits_emotion_jump(item.production_note))
                level = target if jump else min(level + 1, target)
                if item.id == line_id:
                    effective_strength = STRENGTH_NAMES[level]
                    break
        warnings = [performance["message"]] if performance.get("message") else []
        if effective_strength != strength:
            warnings.append(f"连续性处理：{strength} → {effective_strength}；剧情需要突变时，在本句指导中明确写“情绪转折”及表达方式。")
        run = self.db.scalar(select(AdaptationRunPO).where(
            AdaptationRunPO.project_id == project_id, AdaptationRunPO.chapter_id == chapter.id,
            AdaptationRunPO.committed_at.is_not(None),
        ).order_by(AdaptationRunPO.committed_at.desc(), AdaptationRunPO.id.desc()).limit(1))
        parsed = (run.parsed_json or {}) if run else {}
        background = settings["story_background"] or parsed.get("logline") or project.description or ""

        def cue(item):
            return {"line_id": item.id, "speaker": roles.get(item.role_id, "旁白"),
                    "text": (item.text_content or "")[:180]}

        context = {
            "background": str(background)[:1200],
            "background_source": "project" if settings["story_background"] else "committed_analysis" if parsed.get("logline") else "project_description",
            "genre": str(parsed.get("genre") or "")[:100],
            "adaptation_instruction": (run.instruction or "")[:400] if run else "",
            "delivery_style": settings["delivery_style"],
            "chapter": chapter.title, "scene": scene,
            "speaker": roles.get(line.role_id, "旁白"),
            "voice_profile": (line.voice_profile or "")[:240],
            "previous_lines": [cue(item) for item in previous],
            "next_lines": [cue(item) for item in following],
            "previous_same_speaker": cue(same_role[-1]) if same_role else None,
            "continuity_enabled": settings["continuity_enabled"],
            "scene_performance": performance,
        }
        if not background:
            warnings.append("尚无全书背景摘要；可在配音设定补充。当前仅使用已有章节、场景和相邻对白，不自动编造摘要。")
        note = line.production_note or ""
        plan = performance.get("plan") or {}
        planned_cue = performance.get("cue") or {}
        character = next((item for item in plan.get("characters", []) if item["speaker"] == context["speaker"]), {})
        beat = next((item for item in plan.get("beats", []) if item["id"] == planned_cue.get("beatId")), {})
        delivery_note = note or planned_cue.get("delivery") or beat.get("delivery") or character.get("baseline") or ""
        reply = next((item for item in rows[start:position] if item.id == planned_cue.get("responds_to_line_id")), None)
        context["reply_to"] = cue(reply) if reply else None
        compact = model.startswith("cosyvoice") and mode == "native"
        if compact:
            # The model has ~50 Chinese characters of instruction budget. Prefer
            # a stable production style and current action, never paste a novel.
            instruction = build_voice_instruction(emotion, effective_strength, delivery_note or settings["delivery_style"], compact=True)
            warnings.append("此音色指令长度有限：请求按完整分句保留基础表演约束，再放本句要求或共同基调；完整上下文保留在记录中，请核对最终请求预览。")
        else:
            instruction = build_voice_instruction(emotion, effective_strength, delivery_note, mode=mode)
            if mode == "native":
                # Keep all source context in the trace, but bound what we ask a
                # speech model to interpret. Never append neighbouring words to text.
                compact_context = {
                    "作品背景": context["background"][:180],
                    "题材": context["genre"],
                    "共同表演基调": context["delivery_style"][:100],
                    "改编要求": context["adaptation_instruction"][:100],
                    "场景": scene[:60],
                    "当前人物": context["speaker"],
                    "声线": context["voice_profile"][:80],
                    "前文": [{**item, "text": item["text"][:70]} for item in context["previous_lines"]],
                    "后文": [{**item, "text": item["text"][:70]} for item in context["next_lines"]],
                    "上次本人发言": ({**context["previous_same_speaker"], "text": context["previous_same_speaker"]["text"][:70]}
                                    if context["previous_same_speaker"] else None),
                }
                if performance["status"] == "current":
                    compact_context["整场表演"] = {
                        "本句意图": planned_cue.get("intent", ""), "人物目标": character.get("objective", ""),
                        "稳定声线": character.get("baseline", ""), "当前阶段": beat.get("purpose", ""),
                        "基调": plan["baseline"], "接话节奏": plan["pace"],
                        "场景任务": plan["purpose"], "人物关系": character.get("relationship", ""),
                        "回应对象": ({"speaker": context["reply_to"]["speaker"], "text": context["reply_to"]["text"][:70]}
                                     if context["reply_to"] else None),
                    }
                    # Keep the full design in the trace, but send an identical
                    # direction only once. Distinct intent and authored notes stay.
                    sent_direction = (delivery_note, compact_context["共同表演基调"], compact_context["声线"])
                    for field in ("本句意图", "基调", "稳定声线"):
                        value = compact_context["整场表演"].get(field, "").strip()
                        if value and any(value in source for source in sent_direction):
                            compact_context["整场表演"].pop(field)
                    # Deliberately exclude future beats and their acting directions.
                instruction, omitted = compile_context_instruction(instruction, compact_context, budget=1600 if model.startswith("qwen3") else 2000)
                if omitted:
                    warnings.append("指导长度控制：以下上下文未送入模型，但完整快照仍保留：" + "、".join(omitted))
            else:
                warnings.append("此音色无法理解完整小说背景；上下文用于本地连续性控制与排查，不会伪装成可执行的原生指令。")
        text = clean_spoken_text(line.text_content)
        overrides = {}
        applied = []
        replacements = {}
        pronunciations = {}
        native_pronunciation = model in {"qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash"} and route != "edge" and not ("payload" in params or "body" in params)
        for entry in settings["pronunciation_entries"]:
            if entry["term"] not in text:
                continue
            if native_pronunciation and entry["pronunciation"]:
                pronunciations[entry["term"]] = entry["pronunciation"]
                applied.append({**entry, "mode": "hot_fix.pronunciation"})
            elif entry["spoken_as"]:
                replacements[entry["term"]] = entry["spoken_as"]
                applied.append({**entry, "mode": "spoken_as"})
            else:
                warnings.append(f"当前模型未接入拼音控制，词条“{entry['term']}”未应用；可填写替代读法。")
        if replacements:
            pattern = "|".join(re.escape(term) for term in sorted(replacements, key=len, reverse=True))
            text = re.sub(pattern, lambda match: replacements[match.group()], text)
        if pronunciations:
            hot_fix = copy.deepcopy(params.get("hot_fix") or {})
            existing = {key: value for item in hot_fix.get("pronunciation", []) for key, value in item.items()}
            hot_fix["pronunciation"] = [{key: value} for key, value in {**existing, **pronunciations}.items()]
            overrides["hot_fix"] = hot_fix
        if not text:
            raise ValueError("处理后的朗读文本为空")
        return {
            "policy_version": POLICY_VERSION, "settings_revision": settings["revision"],
            "provider_id": provider_id, "model": model, "voice_id": voice.id if voice else None,
            "voice_name": voice_name, "route": route, "mode": mode, "context": context,
            "original_text": line.text_content, "tts_text": text, "production_note": note, "delivery_note": delivery_note,
            "emotion": emotion, "original_strength": strength, "effective_strength": effective_strength,
            "instruction": instruction, "provider_overrides": overrides,
            "pronunciation_applied": applied, "warnings": warnings,
        }

    def preview(self, project_id, line_id):
        from app.services.speech import routing as speech_routing
        prepared = self.prepare(project_id, line_id)
        provider = self.db.get(TTSProviderPO, prepared["provider_id"])
        line, _ = self.line(project_id, line_id)
        role = self.db.get(RolePO, line.role_id) if line.role_id else None
        voice = self.db.get(VoicePO, prepared["voice_id"]) if prepared["voice_id"] else None
        if prepared["route"] == "edge":
            prepared["request_preview"] = {
                "driver": "edge", "text": prepared["tts_text"],
                "voice": speech_routing.resolve_edge_voice(role, voice),
                **edge_prosody(prepared["emotion"], prepared["effective_strength"], prepared["delivery_note"]),
            }
        elif provider.provider_type in {"fish", "legacy", "index_tts"}:
            prepared["request_preview"] = {"driver": "legacy", "method": "POST",
                "url": f"{provider.api_base_url.rstrip('/')}/v2/synthesize",
                "payload": TTSEngine.request_payload(prepared["tts_text"], voice.reference_path if voice else None,
                    emo_vector=emotion_text_to_vector(prepared["emotion"], prepared["effective_strength"]))}
        else:
            params = ConfigurableCloudTTSEngine._parse_params(provider.custom_params)
            engine = ConfigurableCloudTTSEngine(provider.api_base_url, provider.api_key, provider.model,
                                                {**params, **prepared["provider_overrides"]})
            prepared["request_preview"] = engine.preview_request(
                prepared["tts_text"], prepared["voice_name"], voice.reference_path if voice else None,
                instruction=prepared["instruction"],
                emo_vector=emotion_text_to_vector(prepared["emotion"], prepared["effective_strength"]))
        return prepared
