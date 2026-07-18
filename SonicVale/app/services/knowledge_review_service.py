from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import ProjectPO
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.article.schemas import ArticleAnalysis, KnowledgeReviewReport, KnowledgeScript


class KnowledgeReviewService:
    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def review(self, project: ProjectPO, source_text: str, analysis: dict[str, Any], script: dict[str, Any]) -> dict[str, Any]:
        validated_analysis = ArticleAnalysis.model_validate(analysis)
        validated_script = KnowledgeScript.model_validate(script)
        system_prompt = "\n\n".join([
            "你是独立的知识音频审查 Agent，不参与脚本创作。",
            "内容准确性：检查结论、限定条件、因果关系、数字和概念是否忠实原文；检查 AI 补充是否正确标记。",
            "学习质量：检查知识顺序、术语解释、例子、总结和回忆节点；不能为了戏剧效果牺牲准确性。",
            "音频质量：检查对话节奏、长段信息倾倒，以及制作提示是否混入朗读文本。dialogue_lesson 必须由知夏女声和闻舟男声通过追问、反例、纠错和复述推进；检查每句情绪与强度是否自然变化，不能全篇平静、不能是一人念稿或另一人只做捧哏。",
            "coverage 必须逐个报告 required 知识点是否被脚本覆盖。只返回符合响应结构的 JSON。",
        ])
        prompt = "\n\n".join([
            f"文章正文：\n{source_text}",
            f"已确认分析：{json.dumps(validated_analysis.model_dump(mode='json'), ensure_ascii=False)}",
            f"待审查脚本：{json.dumps(validated_script.model_dump(mode='json'), ensure_ascii=False)}",
        ])
        result = self.llm.call_json(project, prompt, system_prompt=system_prompt, response_model=KnowledgeReviewReport, schema_name="knowledge_review")
        report = KnowledgeReviewReport.model_validate(result).model_dump(mode="json")
        required_ids = {point.id for point in validated_analysis.key_points if point.importance == "required"}
        covered_ids = {
            point_id
            for segment in validated_script.segments
            for point_id in segment.knowledge_point_ids
        } | {
            point_id
            for segment in validated_script.segments
            for line in segment.lines
            for point_id in line.knowledge_point_ids
        }
        missing = sorted(required_ids - covered_ids)
        forbidden_labels = ("[原文观点]", "[AI 解释]", "[AI解释]", "[外部资料补充]", "[待确认]")
        polluted_lines = [
            line.text
            for segment in validated_script.segments
            for line in segment.lines
            if line.should_speak and any(label in line.text for label in forbidden_labels)
        ]
        if missing:
            report["issues"].append({"severity": "error", "category": "知识覆盖", "message": f"遗漏必须知识点：{', '.join(missing)}"})
        if polluted_lines:
            report["issues"].append({"severity": "error", "category": "TTS 文本", "message": "朗读文本包含内容来源或制作标签"})
        dialogue_issues: list[str] = []
        if validated_script.adaptation_mode == "dialogue_lesson":
            spoken = [line for segment in validated_script.segments for line in segment.lines if line.should_speak]
            dialogue = [line for line in spoken if line.type == "dialogue"]
            speakers = {line.speaker for line in dialogue}
            total_chars = sum(len(line.text) for line in spoken) or 1
            dialogue_chars = sum(len(line.text) for line in dialogue)
            if speakers != {"知夏", "闻舟"}:
                dialogue_issues.append("未严格使用知夏、闻舟两位固定学习搭档")
            if dialogue_chars / total_chars < 0.8:
                dialogue_issues.append("对话字数不足 80%，仍然接近旁白念稿")
            if any(len(line.text) > 220 for line in spoken):
                dialogue_issues.append("存在超过 220 字的单条长篇念稿")
            emotions = {line.emotion for line in dialogue if line.emotion}
            if len(emotions) < 3:
                dialogue_issues.append("对话情绪变化不足 3 种，听感仍会接近机器人念稿")
            if any(not line.strength or not line.production_note for line in dialogue):
                dialogue_issues.append("部分对话缺少情绪强度或声音指导")
        for message in dialogue_issues:
            report["issues"].append({"severity": "error", "category": "对话质量", "message": message})
        if missing or polluted_lines or dialogue_issues or report["unmarked_supplements"]:
            report["passed"] = False
        return report
