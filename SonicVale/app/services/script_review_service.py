from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.prompts import get_audio_drama_adaptation_rules
from app.models.po import ProjectPO
from app.services.workflow_llm_service import WorkflowLLMService
from app.workflows.drama.schemas import ScriptReviewReport


class ScriptReviewService:
    """Independent, read-only quality gate for a generated audio-drama script."""

    def __init__(self, db: Session):
        self.llm = WorkflowLLMService(db)

    def review(
        self,
        project: ProjectPO,
        parsed: dict[str, Any],
        roles: list[dict[str, Any]],
        source_text: str,
        script: dict[str, Any],
        known_issues: list[str] | None = None,
    ) -> dict[str, Any]:
        system_prompt = "\n\n".join([
            "你是 Auralis 的广播剧剧本审查员。你不改稿，只做独立验收并输出结构化审查报告。",
            get_audio_drama_adaptation_rules(),
            "审查时把听众视为只能听见声音、完全看不到画面的人。所有必要信息必须能由对白、动作声、环境音、音乐、呼吸、沉默或听觉转场获得。",
            "逐项检查：叙述是否能转成对白；心理活动是否已外化；环境信息是否嵌入可听元素；时空跳转是否有听觉标记；纯视觉描写是否删除或转为可听证据。",
            "特殊场景检查：电话要能听懂通话关系；自言自语要有声音层次；多人场景要能分辨说话者；内心独白应标注声音层；沉默必须保留环境声。",
            "禁止项：作者直接评述、无声音支撑的时间跳跃、纯视觉表情或眼神、角色机械复述信息、说明性对白、同一信息由对白和旁白重复。",
            "同时检查原作关键因果、人物动机和角色口吻是否保持；不要因为追求零旁白而制造不自然的解释性对白。",
            "error 表示交付前必须修复；warning 表示明显影响听觉表达；suggestion 表示可选优化。只有没有 error、核心规范均满足且总分不低于80时 passed 才能为 true。",
            "只返回符合响应结构的 JSON，不要改写或附带完整剧本。",
        ])
        prompt = "\n\n".join([
            f"小说解析：{json.dumps(parsed, ensure_ascii=False)}",
            f"已确认角色：{json.dumps(roles, ensure_ascii=False)}",
            f"小说原文：{source_text}",
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
        if any(item.get("severity") == "error" for item in report["issues"]):
            report["passed"] = False
            report["score"] = min(report["score"], 79)
        return report
