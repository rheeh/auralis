from __future__ import annotations

import json
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dto.line_dto import LineCreateDTO
from app.models.po import (
    AdaptationRunPO,
    ChatMessagePO,
    ChatSessionPO,
    LinePO,
    ProjectPO,
    RolePO,
    TTSProviderPO,
    VoicePO,
)
from app.services.audio_task_service import AudioTaskService
from app.services.drama_workflow_service import DramaWorkflowService, WorkflowConflictError
from app.services.workflow_llm_service import WorkflowLLMError, WorkflowLLMService
from app.workflows.drama.events import WorkflowEventPublisher


ToolName = Literal[
    "get_project_status",
    "list_roles_and_voices",
    "inspect_lines",
    "revise_current_draft",
    "update_line",
    "bind_role_voice",
    "generate_missing_audio",
    "regenerate_line_audio",
    "retry_failed_audio",
    "play_audio",
]


class AssistantToolCall(BaseModel):
    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class AssistantPlan(BaseModel):
    reply: str = ""
    tool_calls: list[AssistantToolCall] = Field(default_factory=list, max_length=4)


class AssistantReply(BaseModel):
    reply: str


ASSISTANT_SYSTEM_PROMPT = "\n\n".join([
    "你是 Auralis 广播剧制作助手。你负责理解用户的制作意图、读取真实项目状态，并在必要时选择受控工具。",
    "不要编造台词 ID、音色 ID、项目状态或执行结果。需要精确对象时先查询。一次最多调用4个工具，不重复相同调用。",
    "写操作必须忠实于用户原意。不要删除章节、角色或台词。用户只是询问时只读，不执行写操作。",
    "角色或剧本确认前，修改意见使用 revise_current_draft；正式写入后使用 inspect_lines、update_line、音色和音频工具。",
    "用户要求修改剧本草稿时，由编剧服务执行修改，随后独立审查服务自动复核；你只负责准确转交意见和汇报结果。",
    "你的制作助手身份与小说解析、角色设计、剧本生成相互隔离；不要自行执行这些任务，只能通过获准的工具进入对应业务流程。",
    "只返回符合响应结构的 JSON。",
])


TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "get_project_status",
        "description": "查询当前改编阶段、草稿、正式章节、台词和音频任务统计。回答进度、缺失项或失败原因前使用。",
        "arguments": {},
    },
    {
        "name": "list_roles_and_voices",
        "description": "列出项目角色、角色当前绑定音色和所有可用音色。回答或执行音色绑定前使用。",
        "arguments": {},
    },
    {
        "name": "inspect_lines",
        "description": "按场景、角色、台词序号、文本片段或状态查询正式台词。修改、重生成或播放指定台词前使用。",
        "arguments": {
            "line_id": "可选，数据库台词 ID",
            "line_order": "可选，章节内显示序号",
            "scene_title": "可选，场景标题的一部分",
            "speaker": "可选，角色名",
            "text_contains": "可选，台词文本片段",
            "status": "可选，pending/processing/done/failed",
            "limit": "可选，1-30，默认20",
        },
    },
    {
        "name": "revise_current_draft",
        "description": "在角色确认或剧本确认阶段，根据用户意见生成新草稿；剧本草稿会自动经过独立规范审查。不要在逐句制作阶段使用。",
        "arguments": {"instruction": "必须，完整且忠实的修改要求"},
    },
    {
        "name": "update_line",
        "description": "修改唯一定位到的正式台词文本或制作备注。修改文本后会把本句标记为待重新生成。",
        "arguments": {
            "line_id": "推荐，台词 ID",
            "line_order": "可选，章节内显示序号",
            "scene_title": "可选",
            "speaker": "可选",
            "text_contains": "可选",
            "text": "可选，新朗读文本",
            "production_note": "可选，新制作/表演提示",
        },
    },
    {
        "name": "bind_role_voice",
        "description": "把一个正式项目角色绑定到指定音色。同一项目中的可朗读角色不得重复使用同一音色。",
        "arguments": {
            "role_id": "可选，角色 ID",
            "role_name": "可选，角色名",
            "voice_id": "可选，音色 ID",
            "voice_name": "可选，音色名",
        },
    },
    {
        "name": "generate_missing_audio",
        "description": "为当前正式章节所有缺失音频的可朗读台词创建 TTS 任务。",
        "arguments": {},
    },
    {
        "name": "regenerate_line_audio",
        "description": "重新生成唯一定位到的一句台词，可同时更新本次生成使用的制作提示。",
        "arguments": {
            "line_id": "推荐，台词 ID",
            "line_order": "可选",
            "scene_title": "可选",
            "speaker": "可选",
            "text_contains": "可选",
            "prompt": "可选，本次表演或生成提示",
        },
    },
    {
        "name": "retry_failed_audio",
        "description": "重试当前会话全部失败的音频任务。",
        "arguments": {},
    },
    {
        "name": "play_audio",
        "description": "请求前端播放整章，或播放唯一定位到的一句已生成音频。此工具只发出界面动作，不修改项目。",
        "arguments": {
            "scope": "all 或 line，默认 all",
            "line_id": "scope=line 时推荐",
            "line_order": "可选",
            "scene_title": "可选",
            "speaker": "可选",
            "text_contains": "可选",
        },
    },
]


class ProductionAssistantAgent:
    """A persistent, project-scoped assistant with a small controlled toolset."""

    MAX_ROUNDS = 3
    TERMINAL_TOOLS = {"revise_current_draft"}

    def __init__(self, db: Session, queue=None):
        self.db = db
        self.queue = queue
        self.llm = WorkflowLLMService(db)
        self.events = WorkflowEventPublisher(db)

    def accept_message(self, session_id: str, message: str, client_request_id: str) -> ChatMessagePO:
        session = self._session(session_id)
        if session.current_stage == "cancelled":
            raise WorkflowConflictError("已取消的会话不能继续操作，请新建改编会话")
        existing = self.db.execute(
            select(ChatMessagePO).where(
                ChatMessagePO.session_id == session_id,
                ChatMessagePO.client_request_id == client_request_id,
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        row = ChatMessagePO(
            id=f"msg_{uuid4().hex}",
            session_id=session_id,
            role="user",
            message_type="text",
            content=message.strip(),
            payload_json={"source": "production_assistant"},
            client_request_id=client_request_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self.events.publish(session, "assistant_message_received", {"message_id": row.id})
        return row

    def run_turn(self, session_id: str, user_message_id: str) -> ChatMessagePO:
        session = self._session(session_id)
        user_message = self.db.get(ChatMessagePO, user_message_id)
        if not user_message or user_message.session_id != session_id or user_message.role != "user":
            raise ValueError("助手消息不存在")

        existing = self.db.execute(
            select(ChatMessagePO).where(
                ChatMessagePO.session_id == session_id,
                ChatMessagePO.role == "assistant",
                ChatMessagePO.client_request_id == f"reply:{user_message_id}",
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        observations: list[dict[str, Any]] = []
        ui_actions: list[dict[str, Any]] = []
        reply = ""
        executed_calls: set[str] = set()
        terminal_tool_completed = False
        try:
            for _ in range(self.MAX_ROUNDS):
                try:
                    plan = self._plan(session, user_message.content or "", observations)
                except WorkflowLLMError:
                    if observations:
                        reply = reply or self._summarize_results(observations)
                        break
                    raise
                if not plan.tool_calls:
                    reply = plan.reply.strip()
                    break
                for call in plan.tool_calls:
                    signature = json.dumps(call.model_dump(), ensure_ascii=False, sort_keys=True)
                    if signature in executed_calls:
                        continue
                    executed_calls.add(signature)
                    result = self._execute_tool(session, call)
                    observations.append({
                        "tool": call.name,
                        "arguments": call.arguments,
                        "result": result,
                    })
                    ui_actions.extend(result.get("ui_actions") or [])
                    terminal_tool_completed = terminal_tool_completed or call.name in self.TERMINAL_TOOLS
                if terminal_tool_completed:
                    # A draft revision already performs the expensive writer + independent reviewer
                    # workflow synchronously. Its result is authoritative, so extra planning/final-reply
                    # model calls only delay the UI and can accidentally propose the same tool again.
                    reply = self._summarize_results(observations)
                    break
                if plan.reply.strip():
                    reply = plan.reply.strip()
            if observations and not terminal_tool_completed:
                try:
                    reply = self._final_reply(session, user_message.content or "", observations, reply)
                except WorkflowLLMError:
                    reply = reply or self._summarize_results(observations)
            if not reply:
                reply = "我已经检查了当前项目，但没有得到足够信息执行操作。请告诉我具体场景、角色或台词序号。"
            message_type = "assistant_action" if observations else "text"
            payload = {
                "in_reply_to": user_message_id,
                "tool_results": observations,
                "ui_actions": self._dedupe_ui_actions(ui_actions),
            }
        except (WorkflowLLMError, WorkflowConflictError, ValueError) as exc:
            reply = f"这次没有执行成功：{exc}"
            message_type = "error"
            payload = {"in_reply_to": user_message_id, "error": str(exc)}
        except Exception:
            reply = "制作助手暂时无法完成这条指令。项目数据没有被进一步修改，请稍后重试。"
            message_type = "error"
            payload = {"in_reply_to": user_message_id, "error": "ASSISTANT_TURN_FAILED"}

        row = ChatMessagePO(
            id=f"msg_{uuid4().hex}",
            session_id=session_id,
            role="assistant",
            message_type=message_type,
            content=reply,
            payload_json=payload,
            client_request_id=f"reply:{user_message_id}",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self.events.publish(session, "assistant_reply_ready", {
            "message_id": row.id,
            "in_reply_to": user_message_id,
            "ui_actions": payload.get("ui_actions", []),
        })
        return row

    def _plan(
        self,
        session: ChatSessionPO,
        user_message: str,
        observations: list[dict[str, Any]],
    ) -> AssistantPlan:
        project = self._project(session.project_id)
        history = self._recent_history(session.id, before_current=user_message)
        context = self._compact_context(session)
        user_prompt = "\n\n".join([
            f"当前项目：{project.name}",
            f"当前上下文：{json.dumps(context, ensure_ascii=False)}",
            f"最近对话：{json.dumps(history, ensure_ascii=False)}",
            f"本轮用户消息：{user_message}",
            f"已经得到的工具观察：{json.dumps(observations, ensure_ascii=False, default=str)}",
            f"可用工具：{json.dumps(TOOL_CATALOG, ensure_ascii=False)}",
            "如果已有工具结果足以回答，tool_calls 必须为空并在 reply 中清楚说明完成了什么、结果是什么、用户下一步可做什么。",
        ])
        return AssistantPlan.model_validate(self.llm.call_json(
            project,
            user_prompt,
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            response_model=AssistantPlan,
            schema_name="production_assistant_plan",
        ))

    def _final_reply(
        self,
        session: ChatSessionPO,
        user_message: str,
        observations: list[dict[str, Any]],
        draft_reply: str,
    ) -> str:
        project = self._project(session.project_id)
        system_prompt = "\n\n".join([
            "你是 Auralis 广播剧制作助手。根据真实工具结果给出简洁中文回复。",
            "不得声称工具结果之外的操作已经完成。失败或歧义要明确说明。只返回符合响应结构的 JSON。",
        ])
        user_prompt = "\n\n".join([
            f"用户要求：{user_message}",
            f"工具结果：{json.dumps(observations, ensure_ascii=False, default=str)}",
            f"先前草稿回复：{draft_reply}",
        ])
        raw = self.llm.call_json(
            project,
            user_prompt,
            system_prompt=system_prompt,
            response_model=AssistantReply,
            schema_name="production_assistant_reply",
        )
        return str(raw.get("reply") or draft_reply or self._summarize_results(observations)).strip()

    def _execute_tool(self, session: ChatSessionPO, call: AssistantToolCall) -> dict[str, Any]:
        handlers = {
            "get_project_status": self._get_project_status,
            "list_roles_and_voices": self._list_roles_and_voices,
            "inspect_lines": self._inspect_lines,
            "revise_current_draft": self._revise_current_draft,
            "update_line": self._update_line,
            "bind_role_voice": self._bind_role_voice,
            "generate_missing_audio": self._generate_missing_audio,
            "regenerate_line_audio": self._regenerate_line_audio,
            "retry_failed_audio": self._retry_failed_audio,
            "play_audio": self._play_audio,
        }
        return handlers[call.name](session, call.arguments)

    def _get_project_status(self, session: ChatSessionPO, _: dict[str, Any]) -> dict[str, Any]:
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        result: dict[str, Any] = {
            "session_id": session.id,
            "project_id": session.project_id,
            "stage": session.current_stage,
            "status": session.status,
            "chapter_id": session.chapter_id,
            "last_error": session.last_error_message,
        }
        if run:
            result["draft_revision"] = run.draft_revision
            result["has_parsed_source"] = bool(run.parsed_json)
            result["has_script_draft"] = bool(run.draft_json)
        if session.chapter_id:
            lines = list(self.db.execute(
                select(LinePO).where(LinePO.chapter_id == session.chapter_id).order_by(LinePO.line_order)
            ).scalars())
            result["lines"] = {
                "total": len(lines),
                "speakable": sum(self._is_speakable(line) for line in lines),
                "done": sum(line.status == "done" for line in lines),
                "failed": sum(line.status == "failed" for line in lines),
                "missing": sum(self._is_speakable(line) and line.status != "done" for line in lines),
            }
            result["audio_tasks"] = AudioTaskService(self.db).summary(session.id)["counts"]
        return self._ok("已读取项目状态", result)

    def _list_roles_and_voices(self, session: ChatSessionPO, _: dict[str, Any]) -> dict[str, Any]:
        roles = list(self.db.execute(
            select(RolePO).where(RolePO.project_id == session.project_id).order_by(RolePO.id)
        ).scalars())
        voices = list(self.db.execute(select(VoicePO).order_by(VoicePO.tts_provider_id, VoicePO.id)).scalars())
        providers = {item.id: item.name for item in self.db.execute(select(TTSProviderPO)).scalars()}
        data = {
            "roles": [{
                "id": role.id,
                "name": role.name,
                "default_voice_id": role.default_voice_id,
                "voice_name": next((voice.name for voice in voices if voice.id == role.default_voice_id), None),
            } for role in roles],
            "voices": [{
                "id": voice.id,
                "name": voice.name,
                "description": voice.description,
                "tts_provider_id": voice.tts_provider_id,
                "provider_name": providers.get(voice.tts_provider_id),
            } for voice in voices],
        }
        if not roles:
            snapshot = DramaWorkflowService(self.db).snapshot(session.id)
            data["draft_roles"] = (snapshot.get("role_drafts") or {}).get("roles", [])
        return self._ok(f"已读取 {len(roles)} 个正式角色和 {len(voices)} 个可用音色", data)

    def _inspect_lines(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        lines = self._matching_lines(session, args, allow_many=True)
        limit = min(max(int(args.get("limit") or 20), 1), 30)
        data = [self._serialize_line(line) for line in lines[:limit]]
        return self._ok(f"找到 {len(lines)} 条符合条件的台词，返回前 {len(data)} 条", data)

    def _revise_current_draft(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        instruction = str(args.get("instruction") or "").strip()
        if not instruction:
            raise ValueError("修改意见不能为空")
        action = {
            "awaiting_role_confirmation": "revise_roles",
            "awaiting_script_confirmation": "revise_script",
        }.get(session.current_stage)
        if not action:
            raise WorkflowConflictError("当前阶段没有可修改的角色或剧本草稿")
        snapshot = DramaWorkflowService(self.db).submit_action(session.id, {
            "action": action,
            "feedback": instruction,
            "payload": {},
            "client_request_id": f"assistant-action-{uuid4().hex}",
        }, record_user_message=False)
        review = snapshot.get("script_review") or {}
        review_summary = (
            f"，独立审查 {review.get('score')} 分并通过"
            if review.get("passed") and review.get("score") is not None
            else "，独立审查已完成"
        )
        return self._ok(
            f"已根据意见生成台本 v{snapshot['draft_revision']}{review_summary}。你可以在版本下拉框中与旧稿对比并自行选用",
            {"stage": snapshot["current_stage"], "draft_revision": snapshot["draft_revision"], "script_review": snapshot.get("script_review")},
            [{"type": "refresh_project"}],
        )

    def _update_line(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        line = self._one_line(session, args)
        text_supplied = "text" in args and args.get("text") is not None
        note_supplied = "production_note" in args
        if not text_supplied and not note_supplied:
            raise ValueError("至少需要提供新台词文本或制作备注")
        if text_supplied:
            text = str(args.get("text") or "").strip()
            if not text:
                raise ValueError("可朗读台词不能为空")
            if re.search(r"[()（）\[\]【】]", text):
                raise ValueError("朗读文本不能包含括号提示，请把提示放到制作备注")
            line.text_content = text
            line.status = "pending"
            line.is_done = 0
            line.active_audio_variant_id = None
        if note_supplied:
            line.production_note = str(args.get("production_note") or "").strip() or None
        self.db.commit()
        self.db.refresh(line)
        return self._ok(
            f"已更新第 {line.line_order} 句",
            self._serialize_line(line),
            [{"type": "focus_line", "line_id": line.id}, {"type": "refresh_project"}],
        )

    def _bind_role_voice(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        role_stmt = select(RolePO).where(RolePO.project_id == session.project_id)
        if args.get("role_id") is not None:
            role_stmt = role_stmt.where(RolePO.id == int(args["role_id"]))
        elif str(args.get("role_name") or "").strip():
            role_stmt = role_stmt.where(RolePO.name == str(args["role_name"]).strip())
        else:
            raise ValueError("需要提供角色名或角色 ID")
        role = self.db.execute(role_stmt).scalar_one_or_none()
        if not role:
            raise ValueError("项目中没有找到该角色")

        voice_stmt = select(VoicePO)
        if args.get("voice_id") is not None:
            voice_stmt = voice_stmt.where(VoicePO.id == int(args["voice_id"]))
        elif str(args.get("voice_name") or "").strip():
            voice_stmt = voice_stmt.where(VoicePO.name == str(args["voice_name"]).strip())
        else:
            raise ValueError("需要提供音色名或音色 ID")
        voices = list(self.db.execute(voice_stmt).scalars())
        if len(voices) != 1:
            raise ValueError("没有唯一定位到音色，请先查询音色列表并使用音色 ID")
        voice = voices[0]
        conflict = self.db.execute(
            select(RolePO).where(
                RolePO.project_id == session.project_id,
                RolePO.id != role.id,
                RolePO.default_voice_id == voice.id,
            )
        ).scalar_one_or_none()
        if conflict:
            raise WorkflowConflictError(f"音色“{voice.name}”已绑定给角色“{conflict.name}”")
        role.default_voice_id = voice.id
        self.db.commit()
        return self._ok(
            f"已将角色“{role.name}”绑定到音色“{voice.name}”",
            {"role_id": role.id, "role_name": role.name, "voice_id": voice.id, "voice_name": voice.name},
            [{"type": "refresh_project"}],
        )

    def _generate_missing_audio(self, session: ChatSessionPO, _: dict[str, Any]) -> dict[str, Any]:
        lines = self._chapter_lines(session)
        self._validate_voice_bindings(session, lines)
        service = AudioTaskService(self.db)
        created: list[str] = []
        skipped = 0
        for line in lines:
            if not self._is_speakable(line) or line.status == "done":
                skipped += 1
                continue
            latest = service.latest_for_line(session.id, line.id)
            if latest and latest.status in {"queued", "processing"}:
                skipped += 1
                continue
            task = service.enqueue(
                self._queue(), session.project_id, session.chapter_id, line, self._line_dto(line), session.id,
                latest if latest and latest.status in {"failed", "cancelled"} else None,
            )
            created.append(task.id)
        return self._ok(
            f"已创建 {len(created)} 条音频任务，跳过 {skipped} 条",
            {"task_ids": created, "created": len(created), "skipped": skipped},
            [{"type": "refresh_project"}],
        )

    def _regenerate_line_audio(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        line = self._one_line(session, args)
        if not self._is_speakable(line):
            raise WorkflowConflictError("音效或 BGM 轨不能生成角色配音")
        if "prompt" in args:
            line.production_note = str(args.get("prompt") or "").strip() or None
        line.status = "pending"
        line.is_done = 0
        line.active_audio_variant_id = None
        self.db.commit()
        service = AudioTaskService(self.db)
        latest = service.latest_for_line(session.id, line.id)
        if latest and latest.status in {"queued", "processing"}:
            raise WorkflowConflictError(f"第 {line.line_order} 句已经在生成队列中")
        task = service.enqueue(
            self._queue(), session.project_id, session.chapter_id, line, self._line_dto(line), session.id,
            latest if latest and latest.status not in {"queued", "processing"} else None,
        )
        return self._ok(
            f"第 {line.line_order} 句已加入重新生成队列",
            {"task_id": task.id, "line": self._serialize_line(line)},
            [{"type": "focus_line", "line_id": line.id}, {"type": "refresh_project"}],
        )

    def _retry_failed_audio(self, session: ChatSessionPO, _: dict[str, Any]) -> dict[str, Any]:
        service = AudioTaskService(self.db)
        failed = [item for item in service.list_for_session(session.id) if item["status"] == "failed"]
        created: list[str] = []
        for item in failed:
            line = self.db.get(LinePO, item["line_id"])
            if not line:
                continue
            task = service.get_for_session(session.id, item["task_id"])
            service.enqueue(
                self._queue(), session.project_id, session.chapter_id, line, self._line_dto(line), session.id, task,
            )
            created.append(task.id)
        return self._ok(
            f"已重试 {len(created)} 条失败音频任务",
            {"task_ids": created},
            [{"type": "refresh_project"}],
        )

    def _play_audio(self, session: ChatSessionPO, args: dict[str, Any]) -> dict[str, Any]:
        if not session.chapter_id:
            raise WorkflowConflictError("剧本写入项目后才能播放音频")
        if str(args.get("scope") or "all") == "all":
            return self._ok("已请求连续播放本章音频", {}, [{"type": "play_all"}])
        line = self._one_line(session, args)
        if line.status != "done":
            raise WorkflowConflictError(f"第 {line.line_order} 句还没有可播放的音频")
        return self._ok(
            f"已请求播放第 {line.line_order} 句",
            self._serialize_line(line),
            [{"type": "play_line", "line_id": line.id}, {"type": "focus_line", "line_id": line.id}],
        )

    def _matching_lines(
        self,
        session: ChatSessionPO,
        args: dict[str, Any],
        *,
        allow_many: bool,
    ) -> list[LinePO]:
        if not session.chapter_id:
            raise WorkflowConflictError("剧本尚未写入项目，目前没有正式台词可查询")
        stmt = select(LinePO).where(LinePO.chapter_id == session.chapter_id)
        if args.get("line_id") is not None:
            stmt = stmt.where(LinePO.id == int(args["line_id"]))
        if args.get("line_order") is not None:
            stmt = stmt.where(LinePO.line_order == int(args["line_order"]))
        if str(args.get("scene_title") or "").strip():
            stmt = stmt.where(LinePO.scene_title.contains(str(args["scene_title"]).strip()))
        if str(args.get("text_contains") or "").strip():
            stmt = stmt.where(LinePO.text_content.contains(str(args["text_contains"]).strip()))
        if str(args.get("status") or "").strip():
            stmt = stmt.where(LinePO.status == str(args["status"]).strip())
        if str(args.get("speaker") or "").strip():
            role_ids = select(RolePO.id).where(
                RolePO.project_id == session.project_id,
                RolePO.name.contains(str(args["speaker"]).strip()),
            )
            stmt = stmt.where(LinePO.role_id.in_(role_ids))
        rows = list(self.db.execute(stmt.order_by(LinePO.line_order)).scalars())
        if not allow_many and not any(args.get(key) is not None and str(args.get(key)).strip() for key in (
            "line_id", "line_order", "scene_title", "speaker", "text_contains",
        )):
            raise ValueError("需要提供台词 ID、序号、场景、角色或文本片段来定位台词")
        return rows

    def _one_line(self, session: ChatSessionPO, args: dict[str, Any]) -> LinePO:
        rows = self._matching_lines(session, args, allow_many=False)
        if not rows:
            raise ValueError("没有找到符合条件的台词")
        if len(rows) > 1:
            candidates = [f"#{line.line_order} {line.text_content}" for line in rows[:8]]
            raise WorkflowConflictError("定位到多条台词，请补充台词序号或 ID：" + "；".join(candidates))
        return rows[0]

    def _chapter_lines(self, session: ChatSessionPO) -> list[LinePO]:
        if not session.chapter_id:
            raise WorkflowConflictError("剧本写入项目后才能操作正式台词")
        return list(self.db.execute(
            select(LinePO).where(LinePO.chapter_id == session.chapter_id).order_by(LinePO.line_order)
        ).scalars())

    def _validate_voice_bindings(self, session: ChatSessionPO, lines: list[LinePO]) -> None:
        role_ids = {line.role_id for line in lines if self._is_speakable(line) and line.role_id}
        roles = list(self.db.execute(select(RolePO).where(RolePO.id.in_(role_ids))).scalars()) if role_ids else []
        missing = [role.name for role in roles if not role.default_voice_id]
        voice_ids = [role.default_voice_id for role in roles if role.default_voice_id]
        if missing:
            raise WorkflowConflictError("请先为这些角色绑定音色：" + "、".join(missing))
        if len(voice_ids) != len(set(voice_ids)):
            raise WorkflowConflictError("不同可朗读角色必须绑定不同音色")

    def _compact_context(self, session: ChatSessionPO) -> dict[str, Any]:
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id) if session.adaptation_run_id else None
        context = {
            "session_id": session.id,
            "project_id": session.project_id,
            "chapter_id": session.chapter_id,
            "stage": session.current_stage,
            "status": session.status,
            "active_confirm_type": session.active_confirm_type,
            "last_error": session.last_error_message,
            "has_script_draft": bool(run and run.draft_json),
        }
        if session.chapter_id:
            context["line_count"] = self.db.execute(
                select(func.count(LinePO.id)).where(LinePO.chapter_id == session.chapter_id)
            ).scalar_one()
        return context

    def _recent_history(self, session_id: str, before_current: str) -> list[dict[str, str]]:
        rows = list(self.db.execute(
            select(ChatMessagePO).where(ChatMessagePO.session_id == session_id)
            .order_by(ChatMessagePO.created_at.desc()).limit(12)
        ).scalars())
        rows.reverse()
        return [
            {"role": row.role, "content": row.content or ""}
            for row in rows
            if row.content and not (row.role == "user" and row.content == before_current and row is rows[-1])
        ]

    def _serialize_line(self, line: LinePO) -> dict[str, Any]:
        role = self.db.get(RolePO, line.role_id) if line.role_id else None
        return {
            "id": line.id,
            "line_order": line.line_order,
            "scene_title": line.scene_title,
            "speaker": role.name if role else None,
            "text": line.text_content,
            "track": line.track,
            "line_type": line.line_type,
            "production_note": line.production_note,
            "status": line.status,
            "has_audio": line.status == "done" and bool(line.audio_path),
            "audio_version_count": len(line.audio_versions or []),
            "active_audio_version_id": line.active_audio_version_id,
        }

    @staticmethod
    def _is_speakable(line: LinePO) -> bool:
        return bool(line.should_speak) and line.track not in {"sfx", "bgm"} and line.line_type not in {"sfx", "bgm"}

    @staticmethod
    def _line_dto(line: LinePO) -> LineCreateDTO:
        return LineCreateDTO.model_validate({column.name: getattr(line, column.name) for column in LinePO.__table__.columns})

    def _queue(self):
        if self.queue is None:
            raise WorkflowConflictError("音频队列当前不可用，请刷新应用后重试")
        return self.queue

    def _session(self, session_id: str) -> ChatSessionPO:
        session = self.db.get(ChatSessionPO, session_id)
        if not session or session.deleted_at is not None:
            raise ValueError("改编会话不存在")
        return session

    def _project(self, project_id: int) -> ProjectPO:
        project = self.db.get(ProjectPO, project_id)
        if not project:
            raise ValueError("项目不存在")
        return project

    @staticmethod
    def _ok(
        summary: str,
        data: Any = None,
        ui_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {"ok": True, "summary": summary, "data": data, "ui_actions": ui_actions or []}

    @staticmethod
    def _summarize_results(observations: list[dict[str, Any]]) -> str:
        return "；".join(str(item.get("result", {}).get("summary") or "操作完成") for item in observations)

    @staticmethod
    def _dedupe_ui_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for action in actions:
            key = json.dumps(action, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(action)
        return result
