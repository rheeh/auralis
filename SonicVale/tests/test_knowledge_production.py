import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.models.po import AdaptationDraftRevisionPO, AdaptationRunPO, ChatSessionPO, ProjectPO
from app.services.article_workflow_service import ArticleWorkflowService
from app.services.chat_session_service import ChatSessionService
from app.services.content_adaptation_service import ContentAdaptationService
from app.services.knowledge_production_service import KnowledgeProductionService
from tests.test_article_workflow import analysis_payload


def learning_plan_payload():
    return {
        "learning_goal": "quick_understanding",
        "target_duration_minutes": 10,
        "adaptation_mode": "dialogue_lesson",
        "recommended_reason": "概念较多，适合通过提问解释。",
        "ordered_knowledge_point_ids": ["k1"],
        "review_moments": [{"after": "k1", "prompt": "回忆向量表示的含义"}],
    }


def script_payload(title="向量检索入门音频"):
    questions = [
        {"id": f"q{i}", "question": f"问题 {i}", "answer": "文本可表示为向量。", "knowledge_point_id": "k1", "source_excerpt": "文本可以表示为向量，再查找相近向量。"}
        for i in range(1, 4)
    ]
    return {
        "title": title,
        "adaptation_mode": "dialogue_lesson",
        "roles": [{"name": "讲解者"}, {"name": "学习者"}],
        "segments": [{
            "id": "seg1", "title": "向量是什么", "segment_type": "knowledge_point",
            "knowledge_point_ids": ["k1"],
            "lines": [
                {"type": "dialogue", "track": "voice", "speaker": "学习者", "text": "向量检索从哪里开始？", "knowledge_point_ids": ["k1"], "content_origin": "ai_explanation"},
                {"type": "dialogue", "track": "voice", "speaker": "讲解者", "text": "先把文本表示为向量。", "knowledge_point_ids": ["k1"], "content_origin": "fact_from_source"},
            ],
        }],
        "review_questions": questions,
    }


def review_payload(passed=True):
    return {
        "passed": passed,
        "accuracy_score": 92,
        "learning_quality_score": 88,
        "audio_quality_score": 90,
        "summary": "知识点覆盖完整，来源标记清楚。",
        "issues": [],
        "coverage": [{"knowledge_point_id": "k1", "covered": True}],
        "unmarked_supplements": [],
    }


class KnowledgeProductionTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/knowledge.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="知识脚本测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def _service(self):
        service = KnowledgeProductionService(self.db)
        service.learning_designer.generate = lambda *args, **kwargs: learning_plan_payload()
        service.script_writer.generate = lambda *args, **kwargs: script_payload()
        service.script_writer.revise = lambda *args, **kwargs: script_payload("向量检索音频·修订")
        service.reviewer.review = lambda *args, **kwargs: review_payload()
        return service

    def test_initial_script_visible_before_review_and_confirmable(self):
        service = self._service()
        observed = {}

        def review_while_visible(*_args, **_kwargs):
            self.db.expire_all()
            session = self.db.get(ChatSessionPO, self.session_id)
            run = self.db.get(AdaptationRunPO, session.adaptation_run_id)
            observed.update(stage=session.current_stage, title=run.draft_json["title"])
            return review_payload()

        service.reviewer.review = review_while_visible
        generated = service.generate_script(self.session_id)
        self.assertEqual(observed, {"stage": "reviewing_knowledge_script", "title": "向量检索入门音频"})
        self.assertEqual(generated["current_stage"], "awaiting_script_confirmation")
        self.assertEqual(generated["knowledge_review"]["accuracy_score"], 92)
        self.assertEqual(len(generated["review_questions"]), 3)
        self.assertEqual(generated["knowledge_script_revisions"][0]["status"], "reviewed")

        confirmed = service.confirm_script(self.session_id, {"script": generated["knowledge_script"]}, "confirm-script")
        duplicate = service.confirm_script(self.session_id, {"script": generated["knowledge_script"]}, "confirm-script")
        self.assertEqual(confirmed["current_stage"], "knowledge_script_ready")
        self.assertEqual(duplicate["current_stage"], "knowledge_script_ready")

    def test_script_revision_preserves_history_and_rechecks(self):
        service = self._service()
        service.generate_script(self.session_id)
        revised = service.revise_script(self.session_id, "讲得更通俗", "revise-script")
        self.assertEqual(revised["knowledge_script"]["title"], "向量检索音频·修订")
        self.assertEqual(len(revised["knowledge_script_revisions"]), 2)
        self.assertEqual(revised["knowledge_script_revisions"][1]["feedback"], "讲得更通俗")
        self.assertEqual(
            self.db.scalar(select(func.count(AdaptationDraftRevisionPO.id)).where(
                AdaptationDraftRevisionPO.session_id == self.session_id,
                AdaptationDraftRevisionPO.draft_type == "knowledge_script",
            )),
            2,
        )


if __name__ == "__main__":
    unittest.main()
