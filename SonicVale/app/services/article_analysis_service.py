from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import ProjectPO
from app.services.article_ingest_service import ArticleIngestService
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.article.schemas import ArticleAnalysis


class ArticleAnalysisService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def analyze(
        self,
        project: ProjectPO,
        source_text: str,
        *,
        article_category: str,
        learning_goal: str,
        target_duration_minutes: int,
        instruction: str | None,
    ) -> dict[str, Any]:
        cleaned = ArticleIngestService.normalize_text(source_text)
        system_prompt = "\n\n".join([
            "你是 Auralis 的知识文章分析 Agent。你的唯一职责是从用户确认的文章正文中提取结构、核心知识点、术语、例子、观点和限制条件。",
            "只基于用户提供的正文进行分析，不联网，不把常识或推测写成原文事实。必须区分 fact_from_source、opinion_from_source、example_from_source、ai_explanation 和 uncertain_claim。",
            "每个核心知识点必须包含原文中真实存在的 source_excerpt，并填写可定位的 source_location；禁止伪造引文。",
            "知识点按学习顺序排列，专业术语首次出现时应说明；保留数字、条件、因果关系和作者的限定措辞。",
            "根据文章特点推荐 audio_lesson、dialogue_lesson 或 knowledge_drama，但不得生成音频脚本。",
            "必须返回非空 sections 和 key_points。只返回符合响应结构的 JSON，不得生成小说角色、场景或广播剧台词。",
        ])
        user_prompt = "\n\n".join([
            f"文章领域：{article_category}",
            f"学习目标：{learning_goal}",
            f"目标音频时长：{target_duration_minutes} 分钟",
            f"用户要求：{instruction or '用清晰、容易理解的方式提炼核心知识。'}",
            f"文章正文：\n{cleaned}",
        ])
        result = self.llm.call_json(
            project,
            user_prompt,
            system_prompt=system_prompt,
            response_model=ArticleAnalysis,
            schema_name="article_analysis",
        )
        return ArticleAnalysis.model_validate(result).model_dump(mode="json")

    def revise(
        self,
        project: ProjectPO,
        source_text: str,
        previous: dict[str, Any],
        feedback: str,
    ) -> dict[str, Any]:
        system_prompt = "\n\n".join([
            "你是 Auralis 的知识大纲修订 Agent。只根据用户反馈修改已生成的文章分析和知识点大纲。",
            "所有保留或新增的知识点仍必须回指用户文章中的真实 source_excerpt；不得引入未标记的外部事实。",
            "未被反馈影响的结构和知识点保持不变。只返回符合响应结构的 JSON。",
        ])
        user_prompt = "\n\n".join([
            f"文章正文：\n{ArticleIngestService.normalize_text(source_text)}",
            f"当前分析与大纲：\n{json.dumps(previous, ensure_ascii=False)}",
            f"用户修改意见：{feedback}",
        ])
        result = self.llm.call_json(
            project,
            user_prompt,
            system_prompt=system_prompt,
            response_model=ArticleAnalysis,
            schema_name="article_analysis_revision",
        )
        return ArticleAnalysis.model_validate(result).model_dump(mode="json")
