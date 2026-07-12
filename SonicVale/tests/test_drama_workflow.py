import asyncio
import os
import tempfile
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.dto.line_dto import LineCreateDTO
from app.models.po import AudioTaskPO, LinePO, ProjectPO, RolePO
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


if __name__ == "__main__":
    unittest.main()
