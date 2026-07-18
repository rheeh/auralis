import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ChatSessionCreateDTO
from app.models.po import AdaptationRunPO, ChatMessagePO, ChatSessionPO, LinePO, ProjectPO, RolePO
from app.services.chat_session_service import ChatSessionService
from app.services.content_adaptation_service import ContentAdaptationService
from app.workflows.article.schemas import ArticleAnalysis


class ContentAdaptationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/content.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="双内容工作流测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
        self.project_id = project.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_legacy_novel_request_keeps_novel_defaults(self):
        snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
            project_id=self.project_id,
            source_text="雨夜里传来敲门声。",
        ))
        session = self.db.get(ChatSessionPO, snapshot["session_id"])
        run = self.db.get(AdaptationRunPO, session.adaptation_run_id)
        self.assertEqual(snapshot["source_type"], "novel")
        self.assertEqual(snapshot["adaptation_mode"], "drama")
        self.assertEqual(session.source_type, "novel")
        self.assertEqual(run.source_kind, "novel")

    def test_article_feature_flag_blocks_creation(self):
        with patch("app.services.chat_session_service.KNOWLEDGE_ARTICLE_ENABLED", False):
            with self.assertRaisesRegex(ValueError, "当前未启用"):
                ChatSessionService(self.db).create(ChatSessionCreateDTO(
                    project_id=self.project_id,
                    source_type="knowledge_article",
                    source_text="这是一篇用于测试的技术文章。",
                ))

    def test_article_session_is_isolated_and_recoverable(self):
        dto = ChatSessionCreateDTO(
            project_id=self.project_id,
            source_type="knowledge_article",
            source_text="向量数据库通过近似最近邻搜索提高检索效率。",
            article_category="technology",
            learning_goal="quick_understanding",
            target_duration_minutes=10,
            verification_mode="source_only",
        )
        with patch("app.services.chat_session_service.KNOWLEDGE_ARTICLE_ENABLED", True):
            created = ChatSessionService(self.db).create(dto)

        self.assertEqual(created["current_stage"], "created")
        ready = ContentAdaptationService(self.db).start(created["session_id"])
        recovered = ContentAdaptationService(self.db).snapshot(created["session_id"])
        self.assertEqual(ready["current_stage"], "source_ready")
        self.assertEqual(recovered["source_type"], "knowledge_article")
        self.assertEqual(recovered["adaptation_mode"], "auto")
        self.assertEqual(recovered["article_category"], "technology")
        self.assertEqual(recovered["target_duration_minutes"], 10)
        self.assertEqual(self.db.scalar(select(func.count(RolePO.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(LinePO.id))), 0)
        self.assertEqual(
            self.db.scalar(select(func.count(ChatMessagePO.id)).where(ChatMessagePO.session_id == created["session_id"])),
            2,
        )
        again = ContentAdaptationService(self.db).start(created["session_id"])
        self.assertEqual(again["current_stage"], "source_ready")

    def test_article_analysis_requires_unique_evidence_backed_points(self):
        payload = {
            "title": "向量检索",
            "summary": "解释向量检索的基本思路。",
            "sections": [{"id": "s1", "title": "原理"}],
            "key_points": [
                {"id": "k1", "title": "向量", "source_excerpt": "文本可以表示为向量。"},
                {"id": "k1", "title": "检索", "source_excerpt": "系统查找相近向量。"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "知识点 id 不能重复"):
            ArticleAnalysis.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
