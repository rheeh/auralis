from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DRAMA_WORKFLOW_MAX_SOURCE_CHARS
from app.models.po import ProjectPO
from app.core.prompts import get_audio_drama_adaptation_rules
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.drama.schemas import SourceAnalysis


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
        if len(text) > DRAMA_WORKFLOW_MAX_SOURCE_CHARS:
            raise ValueError(f"小说正文不能超过 {DRAMA_WORKFLOW_MAX_SOURCE_CHARS} 字")
        return text

    def parse(self, project: ProjectPO, source_text: str, instruction: str | None = None) -> dict[str, Any]:
        cleaned = self.clean(source_text)
        system_prompt = "\n\n".join([
            "你是 Auralis 的小说内容解析 Agent。你的唯一职责是把小说原文分析为可供广播剧角色设计和剧本生成使用的结构化资料。",
            get_audio_drama_adaptation_rules(),
            "逐句完成 contentMap 分类；先判断听觉功能，再识别人物、场景、事件、冲突和声音线索。不要在解析阶段默认保留小说叙述。",
            "小说正文就是完整分析依据。必须至少输出一个人物、一个场景和一条 contentMap；不得返回 status、message、insufficient_information 或空数组来代替分析。",
            "不得续写、改写小说或执行制作工具。只返回符合响应结构的 JSON。",
        ])
        user_prompt = "\n\n".join([
            f"用户改编要求：{instruction or '保留关键情节，适合广播剧制作。'}",
            f"小说正文：\n{cleaned}",
        ])
        parsed = self.llm.call_json(
            project,
            user_prompt,
            system_prompt=system_prompt,
            response_model=SourceAnalysis,
            schema_name="source_analysis",
        )
        return SourceAnalysis.model_validate(parsed).model_dump()
