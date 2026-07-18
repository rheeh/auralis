import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.dto.line_dto import LineCreateDTO
from app.models.po import AudioTaskPO, ChatSessionPO, LinePO, ProjectPO, RolePO
from app.services.article_workflow_service import ArticleWorkflowService
from app.services.audio_task_service import AudioTaskService
from app.services.chat_session_service import ChatSessionService
from app.services.content_adaptation_service import ContentAdaptationService
from app.services.knowledge_commit_service import KnowledgeCommitService
from app.services.knowledge_production_service import KnowledgeProductionService
from app.services.knowledge_study_service import KnowledgeStudyService
from tests.test_article_workflow import analysis_payload
from tests.test_knowledge_production import learning_plan_payload, review_payload, script_payload


class KnowledgeCommitTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/commit.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="知识提交测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
        self.project_id = project.id
        with patch("app.services.chat_session_service.KNOWLEDGE_ARTICLE_ENABLED", True):
            created = ChatSessionService(self.db).create(ChatSessionCreateDTO(
                project_id=project.id, source_type="knowledge_article",
                source_text="文本可以表示为向量，再查找相近向量。",
            ))
        self.session_id = created["session_id"]
        ContentAdaptationService(self.db).start(self.session_id)
        article = ArticleWorkflowService(self.db)
        article.analyzer.analyze = lambda *args, **kwargs: analysis_payload()
        analyzed = article.analyze(self.session_id)
        article.confirm_outline(self.session_id, {"analysis": analyzed["article_analysis"]}, "confirm-outline")
        production = KnowledgeProductionService(self.db)
        production.learning_designer.generate = lambda *args, **kwargs: learning_plan_payload()
        production.script_writer.generate = lambda *args, **kwargs: script_payload()
        production.reviewer.review = lambda *args, **kwargs: review_payload()
        generated = production.generate_script(self.session_id)
        production.confirm_script(self.session_id, {"script": generated["knowledge_script"]}, "confirm-script")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_idempotent_commit_preserves_knowledge_line_mapping_and_tts_queue(self):
        service = KnowledgeCommitService(self.db)
        first = service.commit_session(self.session_id)
        second = service.commit_session(self.session_id)
        self.assertFalse(first["already_committed"])
        self.assertTrue(second["already_committed"])
        self.assertEqual(first["line_count"], 2)
        self.assertEqual(self.db.scalar(select(func.count(RolePO.id))), 2)

        lines = self.db.execute(select(LinePO).where(LinePO.chapter_id == first["chapter_id"]).order_by(LinePO.line_order)).scalars().all()
        self.assertEqual(lines[0].knowledge_metadata["knowledge_point_ids"], ["k1"])
        self.assertEqual(lines[1].knowledge_metadata["content_origin"], "fact_from_source")
        session = self.db.get(ChatSessionPO, self.session_id)
        self.assertEqual(session.current_stage, "completed")

        queue = asyncio.Queue(maxsize=4)
        dto = LineCreateDTO.model_validate({column.name: getattr(lines[0], column.name) for column in LinePO.__table__.columns})
        task = AudioTaskService(self.db).enqueue(queue, self.project_id, first["chapter_id"], lines[0], dto, self.session_id)
        self.assertEqual(task.status, "queued")
        self.assertEqual(self.db.scalar(select(func.count(AudioTaskPO.id))), 1)

    def test_study_queries_and_answer_storage(self):
        KnowledgeCommitService(self.db).commit_session(self.session_id)
        study = KnowledgeStudyService(self.db)
        points = study.knowledge_points(self.session_id)
        questions = study.review_questions(self.session_id)
        self.assertEqual(points[0]["script_lines"][0]["segment_title"], "向量是什么")
        self.assertEqual(len(questions), 3)
        answer = study.answer_question(self.session_id, questions[0]["id"], questions[0]["answer"])
        self.assertTrue(answer["matches_reference"])
        self.assertIn("不代表已经掌握", answer["note"])
        recovered = study.review_questions(self.session_id)
        self.assertEqual(len(recovered[0]["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
