from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DRAMA_WORKFLOW_MAX_DRAFT_CHARS
from app.models.po import ProjectPO
from app.core.prompts import get_audio_drama_adaptation_rules
from app.core.tts_guidance import EMOTION_NAMES, STRENGTH_NAMES
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
        system_prompt = "\n\n".join([
            "你是 Auralis 的广播剧剧本 Agent。你的唯一职责是根据已解析素材和已确认角色生成可直接编辑、配音和后期制作的广播剧剧本。",
            get_audio_drama_adaptation_rules(),
            "dialogue/narration 的 shouldSpeak=true；sfx/bgm 的 shouldSpeak=false，且不能写成可朗读台词。",
            "所有 dialogue/narration 的 text 必须是直接送入 TTS 的100%纯净朗读文本：只允许汉字和正常标点，绝对禁止出现 ()、（）、[]、【】及其中的停顿、音效、情绪或表演提示。",
            "停顿、重音、语速、语气写入 productionNote；音效、环境音、BGM、混响和静音写入 audioEvents，绝对不能混进 text。",
            "audioEvents 每项必须给出 timing、type、content、volume_db；环境底噪通常 -28dB，普通声音 -18dB 至 -24dB，前景音效约 -12dB。",
            f"emotion 必须从以下候选中选择：{'、'.join(EMOTION_NAMES)}。strength 表示情绪/表达强度，必须从以下候选中选择：{'、'.join(STRENGTH_NAMES)}。",
            "严格参考小说解析中的 contentMap：audioStrategy=delete 的内容不要换个说法塞回旁白；audioStrategy=sfx/bgm 的内容必须进入对应非朗读轨。",
            "每个场景必须把对白、旁白、SFX 和 BGM 按播放顺序统一放进 scenes[].lines。禁止使用 scenes[].dialogues、scenes[].audioEvents 或其他平行数组代替 lines。",
            "每场生成后做旁白审计：禁止连续旁白；单条旁白通常不超过45个汉字；旁白字数目标不超过人物可朗读文本的15%。",
            "不得重新执行小说解析、修改项目数据库或调用制作工具。只返回符合响应结构的 JSON。",
        ])
        parts = [
            f"用户要求：{instruction or '生成可直接编辑和配音的广播剧剧本。'}",
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
            f"已确认角色：{json.dumps(roles, ensure_ascii=False)}",
            f"小说正文：{source_text}",
        ]
        if previous_script:
            parts.append(f"当前剧本草稿：{json.dumps(previous_script, ensure_ascii=False)}")
        if feedback:
            parts.extend([f"用户修改意见：{feedback}", "优先局部重写受影响的台词或场景，其他内容保持稳定。"])
        raw = self.llm.call_json(
            project,
            "\n\n".join(parts),
            system_prompt=system_prompt,
            response_model=DramaScript,
            schema_name="drama_script",
        )
        script = DramaScript.model_validate(raw).model_dump()
        # Programmatic narration findings are handed to the independent reviewer.
        # Keeping repair in DramaWorkflowService avoids a second, overlapping
        # self-review call before the actual quality gate.
        self._ensure_sound_prompts(script)
        if len(json.dumps(script, ensure_ascii=False)) > DRAMA_WORKFLOW_MAX_DRAFT_CHARS:
            raise ValueError(f"剧本草稿不能超过 {DRAMA_WORKFLOW_MAX_DRAFT_CHARS} 字")
        return script

    def revise_from_review(
        self,
        project: ProjectPO,
        parsed: dict[str, Any],
        roles: list[dict[str, Any]],
        source_text: str,
        script: dict[str, Any],
        review: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = "\n\n".join([
            "你是 Auralis 的广播剧编剧返修 Agent。你只根据独立审查报告修订现有草稿，不重新解析小说。",
            get_audio_drama_adaptation_rules(),
            "逐条解决 error 和 warning：把可替代叙述变成自然对白或声音行动；外化心理活动；为时空跳转补听觉标记；删除或转化纯视觉描述。",
            "禁止用角色解释双方都知道的信息，禁止为了零旁白制造不自然的说明性台词。保留原作关键因果、人物动机、场景顺序和已经自然的对白。",
            "朗读 text 必须保持纯净；表演提示进入 productionNote，声音设计进入 audioEvents。",
            "只返回符合响应结构的完整修订剧本 JSON。",
        ])
        prompt = "\n\n".join([
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
            f"已确认角色：{json.dumps(roles, ensure_ascii=False)}",
            f"小说原文：{source_text}",
            f"当前剧本：{json.dumps(script, ensure_ascii=False)}",
            f"独立审查报告：{json.dumps(review, ensure_ascii=False)}",
        ])
        revised = DramaScript.model_validate(self.llm.call_json(
            project,
            prompt,
            system_prompt=system_prompt,
            response_model=DramaScript,
            schema_name="review_revised_drama_script",
        )).model_dump()
        self._ensure_sound_prompts(revised)
        if len(json.dumps(revised, ensure_ascii=False)) > DRAMA_WORKFLOW_MAX_DRAFT_CHARS:
            raise ValueError(f"剧本草稿不能超过 {DRAMA_WORKFLOW_MAX_DRAFT_CHARS} 字")
        return revised

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
