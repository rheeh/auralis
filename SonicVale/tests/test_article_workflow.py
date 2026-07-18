import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.models.po import AdaptationDraftRevisionPO, ProjectPO
from app.services.article_workflow_service import ArticleWorkflowService
from app.services.chat_session_service import ChatSessionService
from app.services.content_adaptation_service import ContentAdaptationService


def analysis_payload(title="向量检索入门"):
    return {
        "title": title,
        "summary": "文章解释向量检索的基本流程。",
        "category": "technology",
        "audience": "初学者",
        "sections": [{"id": "s1", "title": "基本原理", "summary": "从向量表示到相似度检索", "source_location": "第 1-2 段"}],
        "key_points": [{
            "id": "k1", "title": "向量表示", "one_sentence_summary": "文本可以转成向量。",
            "explanation": "模型将文本映射为数值向量。", "importance": "required",
            "source_excerpt": "文本可以表示为向量，再查找相近向量。", "source_location": "第 1 段",
            "audio_order": 1, "content_origin": "fact_from_source", "is_ai_supplement": False,
        }],
        "recommended_format": "dialogue_lesson",
        "recommended_duration": 10,
    }


class ArticleWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/workflow.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="知识工作流测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
        self.project_id = project.id
        with patch("app.services.chat_session_service.KNOWLEDGE_ARTICLE_ENABLED", True):
            created = ChatSessionService(self.db).create(ChatSessionCreateDTO(
                project_id=self.project_id,
                source_type="knowledge_article",
                source_text="文本可以表示为向量，再查找相近向量。",
                article_category="technology",
            ))
        self.session_id = created["session_id"]
        ContentAdaptationService(self.db).start(self.session_id)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def _workflow(self):
        service = ArticleWorkflowService(self.db)
        service.analyzer.analyze = lambda *args, **kwargs: analysis_payload()
        service.analyzer.revise = lambda *args, **kwargs: analysis_payload("向量检索入门·修订")
        return service

    def test_analysis_confirmation_and_recovery_snapshot(self):
        workflow = self._workflow()
        analyzed = workflow.analyze(self.session_id)
        recovered = ArticleWorkflowService(self.db).snapshot(self.session_id)
        self.assertEqual(analyzed["current_stage"], "awaiting_outline_confirmation")
        self.assertEqual(recovered["article_analysis"]["key_points"][0]["source_excerpt"], "文本可以表示为向量，再查找相近向量。")
        self.assertEqual(len(recovered["outline_revisions"]), 1)

        confirmed = workflow.confirm_outline(
            self.session_id,
            {"analysis": analyzed["article_analysis"]},
            "confirm-outline-1",
        )
        duplicate = workflow.confirm_outline(
            self.session_id,
            {"analysis": analyzed["article_analysis"]},
            "confirm-outline-1",
        )
        self.assertEqual(confirmed["current_stage"], "outline_ready")
        self.assertEqual(duplicate["current_stage"], "outline_ready")
        self.assertEqual(
            self.db.scalar(select(func.count(AdaptationDraftRevisionPO.id)).where(
                AdaptationDraftRevisionPO.session_id == self.session_id,
                AdaptationDraftRevisionPO.draft_type == "article_outline",
            )),
            2,
        )

    def test_outline_revision_keeps_revision_history(self):
        workflow = self._workflow()
        workflow.analyze(self.session_id)
        revised = workflow.revise_outline(
            self.session_id,
            "标题更适合初学者",
            {},
            "revise-outline-1",
        )
        self.assertEqual(revised["current_stage"], "awaiting_outline_confirmation")
        self.assertEqual(revised["article_analysis"]["title"], "向量检索入门·修订")
        self.assertEqual(len(revised["outline_revisions"]), 2)
        self.assertEqual(revised["outline_revisions"][1]["feedback"], "标题更适合初学者")


if __name__ == "__main__":
    unittest.main()
