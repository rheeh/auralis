from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DRAMA_GRAPH_MAX_DRAFT_CHARS
from app.models.po import ProjectPO
from app.core.prompts import get_audio_drama_adaptation_rules
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.drama.schemas import DramaScript


class ScriptDraftService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def generate(
        self,
        project: ProjectPO,
        parsed: dict[str, Any],
        roles: list[dict[str, Any]],
        source_text: str,
        instruction: str | None = None,
        previous_script: dict[str, Any] | None = None,
        feedback: str = "",
    ) -> dict[str, Any]:
        schema = {
            "title": "作品名", "logline": "一句话看点", "characters": [{"name": "角色名", "voiceProfile": "声线建议"}],
            "scenes": [{"title": "场景名", "location": "地点", "mood": "情绪", "lines": [{
                "type": "dialogue|narration|sfx|bgm", "track": "voice|narration|sfx|bgm",
                "shouldSpeak": True, "speaker": "角色名/旁白/音效/BGM", "text": "内容",
                "emotion": "情绪", "strength": "强度", "voiceProfile": "声线建议",
                "soundPrompt": "独立音效轨提示", "productionNote": "仅供配音/后期使用的语速、停顿、重音、表演提示",
                "audioEvents": [{"timing": "开场/台词前/台词中XX字后/台词后/停顿期间", "type": "sfx|amb|bgm|reverb|break", "content": "具体声音内容", "volume_db": "-18dB"}],
            }]}],
        }
        parts = [
            "你是广播剧剧本 Agent。只输出严格 JSON。",
            get_audio_drama_adaptation_rules(),
            "dialogue/narration 的 shouldSpeak=true；sfx/bgm 的 shouldSpeak=false，且不能写成可朗读台词。",
            "所有 dialogue/narration 的 text 必须是直接送入 TTS 的100%纯净朗读文本：只允许汉字和正常标点，绝对禁止出现 ()、（）、[]、【】及其中的停顿、音效、情绪或表演提示。",
            "停顿、重音、语速、语气写入 productionNote；音效、环境音、BGM、混响和静音写入 audioEvents，绝对不能混进 text。",
            "audioEvents 每项必须给出 timing、type、content、volume_db；环境底噪通常 -28dB，普通声音 -18dB 至 -24dB，前景音效约 -12dB。",
            "严格参考小说解析中的 contentMap：audioStrategy=delete 的内容不要换个说法塞回旁白；audioStrategy=sfx/bgm 的内容必须进入对应非朗读轨。",
            "每场生成后做旁白审计：禁止连续旁白；单条旁白通常不超过45个汉字；旁白字数目标不超过人物可朗读文本的15%。",
            f"用户要求：{instruction or '生成可直接编辑和配音的广播剧剧本。'}",
            f"JSON schema: {json.dumps(schema, ensure_ascii=False)}",
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
            f"已确认角色：{json.dumps(roles, ensure_ascii=False)}",
            f"小说正文：{source_text}",
        ]
        if previous_script:
            parts.append(f"当前剧本草稿：{json.dumps(previous_script, ensure_ascii=False)}")
        if feedback:
            parts.extend([f"用户修改意见：{feedback}", "优先局部重写受影响的台词或场景，其他内容保持稳定。"])
        raw = self.llm.call_json(project, "\n\n".join(parts))
        script = DramaScript.model_validate(raw).model_dump()
        narration_issues = self._narration_issues(script)
        if narration_issues:
            audit_prompt = "\n\n".join([
                "你是广播剧声音审校 Agent。只输出修订后的严格 JSON，不要解释。",
                get_audio_drama_adaptation_rules(),
                "当前草稿未通过旁白审计：" + "；".join(narration_issues),
                "只修正声音表达：把可替代的旁白改成自然对白、SFX、BGM、停顿或直接删除。保留剧情因果、人物动机、场景顺序和已经自然的对白。",
                "同时逐条清洗朗读 text：括号提示、音效、停顿、混响必须迁移到 productionNote 或 audioEvents，text 中不得留下任何括号。",
                "禁止用角色说明性独白机械替换旁白；角色说话必须符合当下意图和关系。",
                f"JSON schema: {json.dumps(schema, ensure_ascii=False)}",
                f"待审校草稿：{json.dumps(script, ensure_ascii=False)}",
            ])
            script = DramaScript.model_validate(self.llm.call_json(project, audit_prompt)).model_dump()
        self._ensure_sound_prompts(script)
        if len(json.dumps(script, ensure_ascii=False)) > DRAMA_GRAPH_MAX_DRAFT_CHARS:
            raise ValueError(f"剧本草稿不能超过 {DRAMA_GRAPH_MAX_DRAFT_CHARS} 字")
        return script

    @staticmethod
    def _ensure_sound_prompts(script: dict[str, Any]) -> None:
        """SFX/BGM are production instructions and must never be committed empty."""
        for scene in script.get("scenes", []):
            scene_title = str(scene.get("title") or "当前场景").strip()
            for line in scene.get("lines", []):
                line_type = str(line.get("type") or line.get("track") or "").lower()
                if line_type not in {"sfx", "bgm"}:
                    continue
                prompt = str(line.get("soundPrompt") or line.get("text") or line.get("productionNote") or "").strip()
                if not prompt:
                    label = "环境与动作音效" if line_type == "sfx" else "氛围音乐"
                    prompt = f"{scene_title}的{label}，与前后台词节奏自然衔接，层次清晰，不遮挡人声。"
                line["soundPrompt"] = prompt
                if not str(line.get("text") or "").strip():
                    line["text"] = prompt

    @staticmethod
    def _narration_issues(script: dict[str, Any]) -> list[str]:
        narration_chars = 0
        dialogue_chars = 0
        long_count = 0
        consecutive_count = 0

        for scene in script.get("scenes", []):
            previous_was_narration = False
            for line in scene.get("lines", []):
                line_type = str(line.get("type") or "dialogue").lower()
                text_length = len("".join(str(line.get("text") or "").split()))
                if line_type == "narration":
                    narration_chars += text_length
                    long_count += int(text_length > 45)
                    consecutive_count += int(previous_was_narration)
                    previous_was_narration = True
                else:
                    if line_type == "dialogue":
                        dialogue_chars += text_length
                    previous_was_narration = False

        issues = []
        spoken_chars = narration_chars + dialogue_chars
        narration_ratio = narration_chars / spoken_chars if spoken_chars else 0
        if narration_chars and (dialogue_chars == 0 or narration_ratio > 0.18):
            issues.append(f"旁白字数占可朗读文本 {narration_ratio:.0%}，目标不超过15%")
        if long_count:
            issues.append(f"有 {long_count} 条旁白超过45字")
        if consecutive_count:
            issues.append(f"有 {consecutive_count} 处连续旁白")
        return issues
