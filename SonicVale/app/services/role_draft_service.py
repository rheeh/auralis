from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import ProjectPO
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.drama.schemas import RoleDraftList


class RoleDraftService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def generate(
        self,
        project: ProjectPO,
        parsed: dict[str, Any],
        previous_roles: list[dict[str, Any]] | None = None,
        feedback: str = "",
    ) -> list[dict[str, Any]]:
        schema = {
            "roles": [{
                "draft_id": "r1", "name": "角色名", "identity": "身份",
                "personality": ["性格"], "relationships": ["与其他人物的关系"],
                "speech_style": "表达特点", "voice_type": "通用声线建议", "selected": True,
            }]
        }
        prompt_parts = [
            "你是广播剧角色设计 Agent。只输出严格 JSON。",
            "角色名不得重复；voice_type 只能描述年龄、音色、节奏和气质，不得模仿真实人物。",
            f"JSON schema: {json.dumps(schema, ensure_ascii=False)}",
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
        ]
        if previous_roles:
            prompt_parts.append(f"当前角色草稿：{json.dumps(previous_roles, ensure_ascii=False)}")
        if feedback:
            prompt_parts.append(f"用户修改意见：{feedback}")
            prompt_parts.append("只修改受反馈影响的角色，其余角色保持不变。")
        raw = self.llm.call_json(project, "\n\n".join(prompt_parts))
        validated = RoleDraftList.model_validate(raw)
        return [role.model_dump() for role in validated.roles]
