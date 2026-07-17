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
        system_prompt = "\n\n".join([
            "你是 Auralis 的广播剧角色设计 Agent。你的唯一职责是根据既有小说解析设计可制作的角色草稿。",
            "角色名不得重复；voice_type 只能描述年龄、音色、节奏和气质，不得模仿真实人物。",
            "小说解析已提供充分信息。必须返回包含非空 roles 数组的对象；不得返回 status、message、characters 或 insufficient_information 来代替角色草稿。",
            "不得重新解析原文、生成剧本或执行制作工具。只返回符合响应结构的 JSON。",
        ])
        prompt_parts = [
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
        ]
        if previous_roles:
            prompt_parts.append(f"当前角色草稿：{json.dumps(previous_roles, ensure_ascii=False)}")
        if feedback:
            prompt_parts.append(f"用户修改意见：{feedback}")
            prompt_parts.append("只修改受反馈影响的角色，其余角色保持不变。")
        raw = self.llm.call_json(
            project,
            "\n\n".join(prompt_parts),
            system_prompt=system_prompt,
            response_model=RoleDraftList,
            schema_name="role_draft",
        )
        validated = RoleDraftList.model_validate(raw)
        return [role.model_dump() for role in validated.roles]
