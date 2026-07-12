from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DRAMA_GRAPH_MAX_SOURCE_CHARS
from app.models.po import ProjectPO
from app.core.prompts import get_audio_drama_adaptation_rules
from app.services.workflow_llm_service import WorkflowLLMService


class SourceParserService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def clean(self, source_text: str) -> str:
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", source_text or "")
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
        if not text:
            raise ValueError("小说正文不能为空")
        if len(text) > DRAMA_GRAPH_MAX_SOURCE_CHARS:
            raise ValueError(f"小说正文不能超过 {DRAMA_GRAPH_MAX_SOURCE_CHARS} 字")
        return text

    def parse(self, project: ProjectPO, source_text: str, instruction: str | None = None) -> dict[str, Any]:
        cleaned = self.clean(source_text)
        schema = {
            "title": "作品名", "logline": "一句话剧情", "genre": "类型", "narratorPointOfView": "旁白视角",
            "characters": [{"name": "角色名", "role": "角色功能", "traits": ["性格"], "motivation": "动机", "voiceClues": "声线线索"}],
            "scenePlan": [{"title": "场景名", "location": "地点", "mood": "情绪", "plotBeats": ["剧情节拍"], "likelySfx": ["音效"], "likelyBgm": "音乐方向"}],
            "contentMap": [{
                "source": "原文句子或信息点", "category": "对话|动作|环境|心理|背景信息|转场|视觉描写",
                "audioStrategy": "dialogue|sfx|bgm|silence|narration|delete", "keepAsNarration": False,
                "reason": "声音化或删除理由",
            }],
        }
        prompt = "\n\n".join([
            "你是小说内容解析 Agent。只输出严格 JSON，不要解释。",
            f"用户改编要求：{instruction or '保留关键情节，适合广播剧制作。'}",
            get_audio_drama_adaptation_rules(),
            "逐句完成 contentMap 分类；先判断听觉功能，再识别人物、场景、事件、冲突和声音线索。不要在解析阶段默认保留小说叙述。",
            f"JSON schema: {json.dumps(schema, ensure_ascii=False)}",
            f"小说正文：\n{cleaned}",
        ])
        parsed = self.llm.call_json(project, prompt)
        parsed.setdefault("characters", [])
        parsed.setdefault("scenePlan", [])
        parsed.setdefault("title", "未命名作品")
        return parsed
