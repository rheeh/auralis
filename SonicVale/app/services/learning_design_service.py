from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import ProjectPO
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.article.schemas import ArticleAnalysis, LearningPlan


class LearningDesignService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def generate(
        self,
        project: ProjectPO,
        analysis: dict[str, Any],
        learning_goal: str,
        target_duration_minutes: int,
        adaptation_mode: str,
    ) -> dict[str, Any]:
        validated = ArticleAnalysis.model_validate(analysis)
        system_prompt = "\n\n".join([
            "你是 Auralis 的知识音频学习设计 Agent。只负责安排知识顺序、音频形式和复习节点，不生成台词。",
            "信息密度高且论点明确优先 audio_lesson；概念多且面向初学者优先 dialogue_lesson；案例丰富的商业管理文章可以使用 knowledge_drama。",
            "必须覆盖所有 required 知识点；学习顺序应先建立前置概念，再解释原因、案例和应用。",
            "只返回符合响应结构的 JSON。",
        ])
        prompt = "\n\n".join([
            f"文章分析：{json.dumps(validated.model_dump(mode='json'), ensure_ascii=False)}",
            f"学习目标：{learning_goal}",
            f"目标时长：{target_duration_minutes} 分钟",
            f"用户选择的表现形式：{adaptation_mode}",
        ])
        result = self.llm.call_json(project, prompt, system_prompt=system_prompt, response_model=LearningPlan, schema_name="learning_plan")
        plan = LearningPlan.model_validate(result).model_dump(mode="json")
        known_ids = {point.id for point in validated.key_points}
        planned_ids = set(plan["ordered_knowledge_point_ids"])
        if not planned_ids.issubset(known_ids):
            raise ValueError("学习设计引用了不存在的知识点")
        required_ids = {point.id for point in validated.key_points if point.importance == "required"}
        if not required_ids.issubset(planned_ids):
            raise ValueError("学习设计遗漏了必须保留的知识点")
        return plan
