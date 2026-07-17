import asyncio
import os
import tempfile
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.dto.line_dto import LineCreateDTO
from app.models.po import AdaptationRunPO, AudioTaskPO, ChatSessionPO, LinePO, ProjectPO, RolePO
from app.services.audio_task_service import AudioTaskService
from app.services.chat_session_service import ChatSessionService
from app.services.drama_commit_service import DramaCommitService
from app.services.drama_workflow_service import DramaWorkflowService, WorkflowConflictError


class DramaWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/business.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="工作流测试项目", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
        self.project_id = project.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def _workflow(self):
        service = DramaWorkflowService(self.db)
        service.source_parser.parse = lambda project, source, instruction: {
            "title": "雨夜", "characters": [{"name": "林默"}], "scenePlan": [{"title": "门外"}],
        }
        service.role_drafter.generate = lambda project, parsed, previous, feedback: [
            {
                "draft_id": "r1", "name": "林默", "identity": "调查员", "personality": ["冷静"],
                "relationships": [], "speech_style": "短句", "voice_type": "青年男声", "selected": True,
            }
        ]
        service.script_drafter.generate = lambda project, parsed, roles, source, instruction, previous, feedback: {
            "title": "雨夜", "logline": "门外有人", "characters": [{"name": "林默"}],
            "scenes": [{
                "title": "门外", "location": "旧屋", "mood": "紧张",
                "lines": [
                    {"type": "sfx", "track": "sfx", "shouldSpeak": False, "speaker": "音效", "text": "三次敲门"},
                    {"type": "dialogue", "track": "voice", "shouldSpeak": True, "speaker": "林默", "text": "谁？"},
                ],
            }],
        }
        service.script_reviewer.review = lambda project, parsed, roles, source, script, known_issues: {
            "passed": True, "score": 92, "summary": "声音表达清晰", "strengths": ["听觉锚点明确"], "issues": [],
        }
        return service

    def test_confirmation_boundary_recovery_and_idempotent_commit(self):
        snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
            project_id=self.project_id,
            title="雨夜",
            source_text="雨落在窗上。门外传来三次敲门声。",
            instruction="悬疑，旁白克制",
        ))
        session_id = snapshot["session_id"]
        workflow = self._workflow()
        role_snapshot = workflow.start(session_id)
        self.assertEqual(role_snapshot["current_stage"], "awaiting_role_confirmation")
        self.assertEqual(self.db.scalar(select(func.count(RolePO.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(LinePO.id))), 0)

        recovered = self._workflow()
        script_snapshot = recovered.submit_action(session_id, {
            "action": "confirm_roles", "feedback": "", "payload": {"roles": role_snapshot["role_drafts"]["roles"]},
            "client_request_id": "confirm-roles-1",
        })
        self.assertEqual(script_snapshot["current_stage"], "awaiting_script_confirmation")
        self.assertEqual(self.db.scalar(select(func.count(RolePO.id))), 0)
        self.assertEqual(len(script_snapshot["script_revisions"]), 1)
        self.assertEqual(script_snapshot["script_revisions"][0]["label"], "初稿")
        self.assertEqual(script_snapshot["script_revisions"][0]["status"], "reviewed")

        ready = recovered.submit_action(session_id, {
            "action": "confirm_script", "feedback": "", "payload": {"script": script_snapshot["script_draft"]},
            "client_request_id": "confirm-script-1",
        })
        self.assertEqual(ready["current_stage"], "script_draft_ready")

        first = DramaCommitService(self.db).commit_session(session_id, "雨夜")
        second = DramaCommitService(self.db).commit_session(session_id, "雨夜")
        self.assertFalse(first["already_committed"])
        self.assertTrue(second["already_committed"])
        self.assertEqual(self.db.scalar(select(func.count(RolePO.id))), 2)
        self.assertEqual(self.db.scalar(select(func.count(LinePO.id))), 2)

        voice_line = self.db.execute(
            select(LinePO).where(LinePO.should_speak == 1).limit(1)
        ).scalar_one()
        queue = asyncio.Queue(maxsize=4)
        audio_service = AudioTaskService(self.db)
        dto = LineCreateDTO.model_validate({column.name: getattr(voice_line, column.name) for column in LinePO.__table__.columns})
        task = audio_service.enqueue(queue, self.project_id, first["chapter_id"], voice_line, dto, session_id)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(task.status, "queued")
        audio_service.mark(task.id, "failed", error=RuntimeError("provider unavailable"))
        failed = audio_service.summary(session_id)
        self.assertEqual(failed["counts"]["failed"], 1)
        retried = audio_service.enqueue(queue, self.project_id, first["chapter_id"], voice_line, dto, session_id, task)
        self.assertEqual(retried.attempt, 2)
        audio_service.mark(task.id, "done", audio_path=voice_line.audio_path)
        reviewed = audio_service.review(session_id, task.id, True, "试听通过")
        self.assertEqual(reviewed.review_status, "approved")
        self.assertEqual(self.db.scalar(select(func.count(AudioTaskPO.id))), 1)

    def test_invalid_stage_action_is_rejected(self):
        snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
            project_id=self.project_id, source_text="测试正文", instruction="测试",
        ))
        with self.assertRaises(WorkflowConflictError):
            self._workflow().submit_action(snapshot["session_id"], {
                "action": "confirm_script", "feedback": "", "payload": {}, "client_request_id": "bad-stage",
            })

    def test_script_is_repaired_and_reviewed_before_user_confirmation(self):
        snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
            project_id=self.project_id, source_text="林小满走进教室，看见陈屿望向窗外。", instruction="零旁白优先",
        ))
        workflow = self._workflow()
        role_snapshot = workflow.start(snapshot["session_id"])
        reports = iter([
            {"passed": False, "score": 68, "summary": "存在纯视觉叙述", "strengths": [], "issues": [{
                "severity": "error", "category": "视觉描述", "scene_title": "门外", "line_index": 1,
                "evidence": "看见角色望向窗外", "suggestion": "改成可听反应",
            }]},
            {"passed": True, "score": 90, "summary": "返修后符合规范", "strengths": ["信息可听"], "issues": []},
        ])
        workflow.script_reviewer.review = lambda *args: next(reports)
        repaired = {**workflow.script_drafter.generate(None, None, None, None, None, None, None), "title": "雨夜·返修"}
        workflow.script_drafter.revise_from_review = lambda *args: repaired

        result = workflow.submit_action(snapshot["session_id"], {
            "action": "confirm_roles", "feedback": "", "payload": {"roles": role_snapshot["role_drafts"]["roles"]},
            "client_request_id": "confirm-roles-review",
        })

        self.assertEqual(result["current_stage"], "awaiting_script_confirmation")
        self.assertEqual(result["script_draft"]["title"], "雨夜·返修")
        self.assertTrue(result["script_review"]["passed"])
        self.assertTrue(result["script_review"]["repair_applied"])
        self.assertEqual(result["script_review"]["initial_score"], 68)
        self.assertEqual([item["label"] for item in result["script_revisions"]], ["初稿", "AI 复核返修稿"])
        self.assertEqual(result["script_revisions"][0]["status"], "needs_repair")
        self.assertEqual(result["script_revisions"][1]["status"], "reviewed")

    def test_initial_script_is_visible_while_independent_review_runs(self):
        snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
            project_id=self.project_id, source_text="雨夜，林默听见三次敲门。", instruction="声音优先",
        ))
        workflow = self._workflow()
        role_snapshot = workflow.start(snapshot["session_id"])
        observed = {}

        def review_during_visible_stage(*args):
            self.db.expire_all()
            session = self.db.get(ChatSessionPO, snapshot["session_id"])
            run = self.db.get(AdaptationRunPO, session.adaptation_run_id)
            observed.update({
                "stage": session.current_stage,
                "draft_title": (run.draft_json or {}).get("title"),
                "snapshot_label": workflow.snapshot(snapshot["session_id"])["script_revisions"][0]["label"],
                "snapshot_status": workflow.snapshot(snapshot["session_id"])["script_revisions"][0]["status"],
            })
            return {"passed": True, "score": 91, "summary": "通过", "strengths": [], "issues": []}

        workflow.script_reviewer.review = review_during_visible_stage
        workflow.submit_action(snapshot["session_id"], {
            "action": "confirm_roles", "feedback": "", "payload": {"roles": role_snapshot["role_drafts"]["roles"]},
            "client_request_id": "confirm-visible-initial",
        })

        self.assertEqual(observed["stage"], "reviewing_script")
        self.assertEqual(observed["draft_title"], "雨夜")
        self.assertEqual(observed["snapshot_label"], "初稿")
        self.assertEqual(observed["snapshot_status"], "reviewing")


if __name__ == "__main__":
    unittest.main()
