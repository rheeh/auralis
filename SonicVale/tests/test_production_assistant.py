import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.po import ChapterPO, ChatSessionPO, LinePO, ProjectPO, RolePO, VoicePO
from app.services.production_assistant_service import (
    AssistantPlan,
    AssistantToolCall,
    ProductionAssistantAgent,
)


class ProductionAssistantTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/assistant.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        project = ProjectPO(name="制作助手测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.flush()
        chapter = ChapterPO(project_id=project.id, title="第一章")
        self.db.add(chapter)
        self.db.flush()
        voice = VoicePO(name="沉稳男声", tts_provider_id=1)
        self.db.add(voice)
        self.db.flush()
        role = RolePO(project_id=project.id, name="林默", default_voice_id=voice.id)
        self.db.add(role)
        self.db.flush()
        line = LinePO(
            chapter_id=chapter.id,
            role_id=role.id,
            line_order=1,
            text_content="谁在门外？",
            line_type="dialogue",
            track="voice",
            should_speak=1,
            scene_title="雨夜门外",
            production_note="克制",
            status="done",
            is_done=1,
            audio_path=f"{self.tempdir.name}/line.wav",
        )
        session = ChatSessionPO(
            id="sess_assistant",
            project_id=project.id,
            chapter_id=chapter.id,
            title="第一章",
            status="completed",
            current_stage="completed",
        )
        self.db.add_all([line, session])
        self.db.commit()
        self.project_id = project.id
        self.line_id = line.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_completed_session_accepts_free_text_and_runs_tools(self):
        agent = ProductionAssistantAgent(self.db)
        user = agent.accept_message(
            "sess_assistant",
            "把第一句改成更警觉的说法。",
            "assistant-request-1",
        )
        plans = iter([
            AssistantPlan(tool_calls=[AssistantToolCall(
                name="inspect_lines",
                arguments={"line_order": 1},
            )]),
            AssistantPlan(tool_calls=[AssistantToolCall(
                name="update_line",
                arguments={"line_id": self.line_id, "text": "谁在那里？"},
            )]),
            AssistantPlan(reply="修改完成。"),
        ])
        agent._plan = lambda session, message, observations: next(plans)
        agent._final_reply = lambda session, message, observations, draft: "已把第一句改为“谁在那里？”，本句需要重新生成音频。"

        reply = agent.run_turn("sess_assistant", user.id)

        line = self.db.get(LinePO, self.line_id)
        self.assertEqual(line.text_content, "谁在那里？")
        self.assertEqual(line.status, "pending")
        self.assertEqual(line.is_done, 0)
        self.assertEqual(reply.role, "assistant")
        self.assertEqual(reply.payload_json["in_reply_to"], user.id)
        self.assertEqual(len(reply.payload_json["tool_results"]), 2)
        self.assertIn({"type": "focus_line", "line_id": self.line_id}, reply.payload_json["ui_actions"])

    def test_message_request_is_idempotent(self):
        agent = ProductionAssistantAgent(self.db)
        first = agent.accept_message("sess_assistant", "现在进度如何？", "same-request")
        second = agent.accept_message("sess_assistant", "重复消息", "same-request")
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.content, "现在进度如何？")

    def test_planning_prompt_separates_fixed_rules_from_turn_context(self):
        class RecordingLLM:
            def __init__(self):
                self.kwargs = None

            def call_json(self, project, user_prompt, **kwargs):
                self.kwargs = {"project": project, "user_prompt": user_prompt, **kwargs}
                return {"reply": "项目正常。", "tool_calls": []}

        agent = ProductionAssistantAgent(self.db)
        agent.llm = RecordingLLM()
        session = self.db.get(ChatSessionPO, "sess_assistant")

        plan = agent._plan(session, "现在进度如何？", [])

        self.assertEqual(plan.reply, "项目正常。")
        self.assertIn("现在进度如何？", agent.llm.kwargs["user_prompt"])
        self.assertIn("可用工具", agent.llm.kwargs["user_prompt"])
        self.assertNotIn("现在进度如何？", agent.llm.kwargs["system_prompt"])
        self.assertEqual(agent.llm.kwargs["schema_name"], "production_assistant_plan")

    def test_draft_revision_stops_after_terminal_tool_without_extra_model_rounds(self):
        session = self.db.get(ChatSessionPO, "sess_assistant")
        session.current_stage = "awaiting_script_confirmation"
        session.status = "active"
        self.db.commit()
        agent = ProductionAssistantAgent(self.db)
        user = agent.accept_message(
            "sess_assistant",
            "只修改第一句，其他内容保持不变。",
            "assistant-request-terminal",
        )
        calls = []

        def plan(current_session, message, observations):
            calls.append((message, list(observations)))
            return AssistantPlan(tool_calls=[AssistantToolCall(
                name="revise_current_draft",
                arguments={"instruction": message},
            )])

        agent._plan = plan
        agent._execute_tool = lambda current_session, call: {
            "ok": True,
            "summary": "已根据意见生成台本 v2，独立审查 92 分并通过。你可以在版本下拉框中与旧稿对比并自行选用",
            "data": {"draft_revision": 2},
            "ui_actions": [{"type": "refresh_project"}],
        }
        agent._final_reply = lambda *args: self.fail("终结工具完成后不应再次调用模型生成回复")

        reply = agent.run_turn("sess_assistant", user.id)

        self.assertEqual(len(calls), 1)
        self.assertIn("台本 v2", reply.content)
        self.assertEqual(reply.payload_json["in_reply_to"], user.id)
        self.assertEqual(reply.payload_json["ui_actions"], [{"type": "refresh_project"}])


if __name__ == "__main__":
    unittest.main()
