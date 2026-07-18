from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.po import ProjectPO
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.article.schemas import ArticleAnalysis, KnowledgeScript, LearningPlan


class KnowledgeScriptService:
    LEARNER = "知夏"
    GUIDE = "闻舟"

    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def generate(
        self,
        project: ProjectPO,
        analysis: dict[str, Any],
        plan: dict[str, Any],
        instruction: str | None = None,
        prior_learning_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        validated_analysis = ArticleAnalysis.model_validate(analysis)
        validated_plan = LearningPlan.model_validate(plan)
        system_prompt = "\n\n".join([
            "你是 Auralis 的知识音频编剧。根据已确认的知识大纲和学习设计生成可直接用于 TTS 的知识脚本。",
            "先讲结论再解释原因；复杂概念给出通俗解释和例子；专业术语首次出现时解释；每隔一段安排自然小结或回忆提示。",
            "默认使用两位长期学习搭档：知夏是会追问、举反例并复述理解的学习者；闻舟是用问题、类比和证据引导的讲解者。角色名必须固定为“知夏”和“闻舟”。",
            "dialogue_lesson 必须是真对话：至少 80% 的可朗读字数来自 dialogue；两人都要实质参与；禁止一人连续长篇念稿、另一人只说“真的吗/原来如此”。单条可朗读台词不超过 220 个汉字。",
            "knowledge_drama 要把原文论点、案例或冲突改造成可理解的场景推进，但不能虚构文章事实。audio_lesson 仅在学习设计明确指定时使用。",
            "只有‘过往学习摘要’明确给出的内容才能被角色回忆；引用时要说明此前文章标题，不得假装记得未提供的文章。",
            "每条台词必须用 knowledge_point_ids 关联知识点，并用 content_origin 标明原文事实、原文观点、原文案例或 AI 解释。不得把 AI 解释写成原文事实。",
            "只使用 1 到 3 个声音。制作提示、音效说明和情绪指导必须放在独立字段，不能混入可朗读 text。",
            "生成 3 到 5 个复习问题；每个答案必须附对应知识点。review_questions.source_excerpt 必须从对应知识点的 source_excerpt 逐字复制，不得概括、改写或拼接。",
            "不得套用小说零旁白、剧情冲突或心理活动外化规则。只返回符合响应结构的 JSON。",
        ])
        prompt = "\n\n".join([
            f"已确认文章分析：{json.dumps(validated_analysis.model_dump(mode='json'), ensure_ascii=False)}",
            f"学习设计：{json.dumps(validated_plan.model_dump(mode='json'), ensure_ascii=False)}",
            f"过往学习摘要：{json.dumps(prior_learning_context or [], ensure_ascii=False)}",
            f"用户补充要求：{instruction or '准确、清晰、适合朗听。'}",
        ])
        result = self.llm.call_json(project, prompt, system_prompt=system_prompt, response_model=KnowledgeScript, schema_name="knowledge_script")
        script = KnowledgeScript.model_validate(result).model_dump(mode="json")
        if validated_plan.adaptation_mode in {"audio_lesson", "dialogue_lesson", "knowledge_drama"}:
            script["adaptation_mode"] = validated_plan.adaptation_mode
        self._validate_links(validated_analysis, script)
        self._validate_dialogue_quality(script)
        return script

    def revise(self, project: ProjectPO, analysis: dict[str, Any], plan: dict[str, Any], previous: dict[str, Any], feedback: str) -> dict[str, Any]:
        system_prompt = "\n\n".join([
            "你是 Auralis 的知识音频脚本修订 Agent。只修改用户反馈涉及的片段，其余内容保持不变。",
            "所有知识点关联、内容来源标签、复习问题答案和原文依据必须继续有效。",
            "不得把制作提示放入朗读文本。只返回符合响应结构的 JSON。",
        ])
        prompt = "\n\n".join([
            f"文章分析：{json.dumps(analysis, ensure_ascii=False)}",
            f"学习设计：{json.dumps(plan, ensure_ascii=False)}",
            f"当前脚本：{json.dumps(previous, ensure_ascii=False)}",
            f"用户修改意见：{feedback}",
        ])
        result = self.llm.call_json(project, prompt, system_prompt=system_prompt, response_model=KnowledgeScript, schema_name="knowledge_script_revision")
        script = KnowledgeScript.model_validate(result).model_dump(mode="json")
        self._validate_links(ArticleAnalysis.model_validate(analysis), script)
        self._validate_dialogue_quality(script)
        return script

    @classmethod
    def _validate_dialogue_quality(cls, script: dict[str, Any]) -> None:
        if script.get("adaptation_mode") != "dialogue_lesson":
            return
        spoken = [
            line
            for segment in script.get("segments", [])
            for line in segment.get("lines", [])
            if line.get("should_speak")
        ]
        dialogue = [line for line in spoken if line.get("type") == "dialogue"]
        speakers = {line.get("speaker") for line in dialogue}
        if speakers != {cls.LEARNER, cls.GUIDE}:
            raise ValueError("对话学习脚本必须由知夏和闻舟两位固定角色共同完成")
        total_chars = sum(len(line.get("text", "")) for line in spoken) or 1
        dialogue_chars = sum(len(line.get("text", "")) for line in dialogue)
        if dialogue_chars / total_chars < 0.8:
            raise ValueError("对话学习脚本旁白过多，至少 80% 的朗读内容必须来自双人对话")
        if any(len(line.get("text", "")) > 220 for line in spoken):
            raise ValueError("对话学习脚本存在超过 220 字的单条念稿，请拆成自然问答")
        counts = {name: sum(1 for line in dialogue if line.get("speaker") == name) for name in (cls.LEARNER, cls.GUIDE)}
        if min(counts.values()) < 3:
            raise ValueError("知夏和闻舟都必须至少有 3 次实质发言")

    @staticmethod
    def _validate_links(analysis: ArticleAnalysis, script: dict[str, Any]) -> None:
        point_map = {point.id: point for point in analysis.key_points}
        known_ids = set(point_map)
        covered: set[str] = set()
        forbidden_labels = ("[原文观点]", "[AI 解释]", "[AI解释]", "[外部资料补充]", "[待确认]")
        for segment in script["segments"]:
            segment_ids = set(segment.get("knowledge_point_ids", []))
            if not segment_ids.issubset(known_ids):
                raise ValueError("知识脚本片段引用了不存在的知识点")
            covered.update(segment_ids)
            for line in segment["lines"]:
                line_ids = set(line.get("knowledge_point_ids", []))
                if not line_ids.issubset(known_ids):
                    raise ValueError("知识脚本台词引用了不存在的知识点")
                covered.update(line_ids)
                if line.get("should_speak") and any(label in line.get("text", "") for label in forbidden_labels):
                    raise ValueError("知识脚本朗读文本不能包含内容来源标签")
        required_ids = {point.id for point in analysis.key_points if point.importance == "required"}
        if not required_ids.issubset(covered):
            raise ValueError("知识脚本遗漏了必须保留的知识点")
        for question in script["review_questions"]:
            point = point_map.get(question["knowledge_point_id"])
            if not point:
                raise ValueError("复习问题引用了不存在的知识点")
            excerpt = question["source_excerpt"].strip()
            source_excerpt = point.source_excerpt.strip()
            if excerpt not in source_excerpt and source_excerpt not in excerpt:
                raise ValueError("复习问题的原文依据与知识点不一致")
