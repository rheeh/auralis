from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.prompts import get_audio_drama_adaptation_rules
from app.services.script_draft_service import ScriptDraftService
from app.models.po import ProjectPO
from app.services.scene_performance_service import project_performance_brief, performance_issues
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.drama.schemas import ScriptReviewReport


class ScriptReviewService:
    """Independent, read-only quality gate for a generated audio-drama script."""

    def __init__(self, db: Session):
        self.db = db
        self.llm = WorkflowLLMService(db)

    def review(
        self,
        project: ProjectPO,
        parsed: dict[str, Any],
        roles: list[dict[str, Any]],
        source_text: str,
        script: dict[str, Any],
        known_issues: list[str] | None = None,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        system_prompt = "\n\n".join([
            "你是 Auralis 的广播剧剧本审查员。你不改稿，只做独立验收并输出结构化审查报告。",
            get_audio_drama_adaptation_rules(),
            "审查时把听众视为只能听见声音、完全看不到画面的人。所有必要信息必须能由对白、必要旁白、动作声、环境音、音乐、呼吸、沉默或听觉转场获得。",
            "旁白比例、超过45字的条数和连续条数仅供观察，不能单独构成 error 或扣分依据。判断是否有叙事功能、重复解释或拖慢节奏，保留用户指定的叙述风格。",
            "逐项检查：叙述是否能转成对白；心理活动是否已外化；环境信息是否嵌入可听元素；时空跳转是否有听觉标记；纯视觉描写是否删除或转为可听证据。",
            "特殊场景检查：电话要能听懂通话关系；自言自语要有声音层次；多人场景要能分辨说话者；内心独白应标注声音层；沉默必须保留环境声。",
            "检查缺陷：没有叙事功能的作者评述、听众无法理解的时间跳跃、未被表达的关键视觉信息、角色机械复述信息、同一信息由对白和旁白无意义重复。",
            "同时检查原作关键因果、人物动机和角色口吻是否保持；不要因为追求零旁白而制造不自然的解释性对白。",
            "逐条核对证据出现顺序、人物在当下知道的信息和结尾未解的身份；提前揭晓或新编关键证据属于 error。角色表、标题、productionNote 给制作人员看，不能视为听众已获知该事实。",
            "检查音效是否真实可制作，是否与 audioEvents 重复，持续环境是否重复进入；先保障听觉因果、自然对白与旁白的叙事功能，不按音效数量或零旁白机械加分。",
            "检查 emotion、strength、productionNote 是否一致：心理紧张不能直接推断可听颤音；日常问答不得仅凭标点标成强烈。普通对白的声音指导可留空或只说明说话目的，不要求每句添加可听变化。无情节或用户依据的逐字强调、机械收尾、反复停顿和省略号，以及哭腔、笑声、喊叫或强度冲突，作为 warning 并给出具体句子与改法；保留用户明确要求的特殊表演。",
            "检查整场 performancePlan 和各句 performanceCue：人物目标与关系应保持稳定，节拍逐步推进，接话对象正确；转折必须有原文或用户依据。不能因后文高潮让前文提前悲愤、哭泣或泄露人物尚不知道的信息。productionNote 与 cue 的发声要求冲突时指出具体句子。",
            "发现关键事实缺失时，evidence 必须指出原文事实和现稿真正可朗读的对应句；禁止脑补。特别核对物件与往事的关联、角色对白归属、先后声音是否被同步、元说明是否被朗读。声音提示中出现整句对白、只有标点的台词也必须报告。",
            "error 表示交付前必须修复；warning 表示明显影响听觉表达；suggestion 表示可选优化。只有没有 error、核心规范均满足且总分不低于80时 passed 才能为 true。",
            "只返回符合响应结构的 JSON，不要改写或附带完整剧本。",
        ])
        prompt = "\n\n".join([
            f"项目表演设定：{json.dumps(project_performance_brief(getattr(self, 'db', None), project), ensure_ascii=False)}",
            f"用户改编与表演要求：{instruction or '遵守默认改编规范。'}",
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
            f"已确认角色：{json.dumps(roles, ensure_ascii=False)}",
            f"小说原文：{source_text}",
            f"旁白描述性统计（不是验收阈值）：{json.dumps(ScriptDraftService.narration_metrics(script), ensure_ascii=False)}",
            f"待审查剧本：{json.dumps(script, ensure_ascii=False)}",
            f"程序化预检发现：{'；'.join(known_issues or []) or '无'}",
        ])
        report = ScriptReviewReport.model_validate(self.llm.call_json(
            project,
            prompt,
            system_prompt=system_prompt,
            response_model=ScriptReviewReport,
            schema_name="audio_drama_script_review",
        )).model_dump()
        for issue in known_issues or []:
            if not any(issue in str(item.get("evidence") or "") for item in report["issues"]):
                report["issues"].append({
                    "severity": "error",
                    "category": "旁白规范",
                    "scene_title": "",
                    "line_index": None,
                    "evidence": issue,
                    "suggestion": "按声音优先规范减少或改写旁白。",
                })
        report["issues"].extend(performance_issues(script, source_text, instruction))
        if any(item.get("severity") == "error" for item in report["issues"]):
            report["passed"] = False
            report["score"] = min(report["score"], 79)
        return report
