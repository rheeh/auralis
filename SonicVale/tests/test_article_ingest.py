import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.chat_dto import ArticleSourceImportDTO, ArticleSourcePreviewDTO, ChatSessionCreateDTO
from app.models.po import ArticleSourcePO, ChatSessionPO, ProjectPO
from app.services.article_ingest_service import ArticleFetchError, ArticleIngestService
from app.services.chat_session_service import ChatSessionService
from app.services.content_adaptation_service import ContentAdaptationService
from app.repositories.project_repository import ProjectRepository


class FakeResponse:
    def __init__(self, *, status=200, url="https://example.com/article", body="", headers=None):
        self.status_code = status
        self.url = url
        self._body = body.encode("utf-8")
        self.headers = headers or {"Content-Type": "text/html; charset=UTF-8"}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def iter_content(self, _):
        yield self._body


class FakeHTTPSession:
    def __init__(self, responses):
        self.responses = iter(responses)

    def get(self, *_args, **_kwargs):
        return next(self.responses)


class ArticleIngestTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AURALIS_CONFIG_DIR"] = self.tempdir.name
        self.engine = create_engine(f"sqlite:///{self.tempdir.name}/article.sqlite3")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        project = ProjectPO(name="文章来源测试", project_root_path=self.tempdir.name)
        self.db.add(project)
        self.db.commit()
        self.project_id = project.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_paste_preview_import_and_session_link(self):
        service = ArticleIngestService(self.db)
        preview = service.preview(ArticleSourcePreviewDTO(
            project_id=self.project_id,
            input_method="paste",
            source_text="技术文章标题\r\n\r\n  第一段介绍。  \n\n\n第二段结论。",
        ))
        self.assertEqual(preview["title"], "技术文章标题")
        self.assertNotIn("\r", preview["normalized_content"])

        imported = service.import_source(ArticleSourceImportDTO(
            project_id=self.project_id,
            input_method="paste",
            title=preview["title"],
            source_text=preview["normalized_content"],
            rights_confirmed=True,
        ))
        with patch("app.services.chat_session_service.KNOWLEDGE_ARTICLE_ENABLED", True):
            snapshot = ChatSessionService(self.db).create(ChatSessionCreateDTO(
                project_id=self.project_id,
                source_type="knowledge_article",
                article_source_id=imported["id"],
            ))
        ready = ContentAdaptationService(self.db).start(snapshot["session_id"])
        source = self.db.get(ArticleSourcePO, imported["id"])
        session = self.db.get(ChatSessionPO, snapshot["session_id"])
        self.assertEqual(source.session_id, session.id)
        self.assertEqual(session.article_source_id, source.id)
        self.assertEqual(ready["source_text"], preview["normalized_content"])

    def test_import_requires_rights_confirmation(self):
        with self.assertRaisesRegex(ValueError, "确认有权"):
            ArticleIngestService(self.db).import_source(ArticleSourceImportDTO(
                project_id=self.project_id,
                input_method="paste",
                source_text="未确认权利的文章正文",
            ))

    def test_instant_workspace_is_reused_and_hidden_from_project_list(self):
        project = self.db.get(ProjectPO, self.project_id)
        project.llm_provider_id = 7
        project.llm_model = "template-model"
        project.tts_provider_id = 9
        self.db.commit()

        service = ArticleIngestService(self.db)
        first = service.ensure_instant_workspace()
        workspace = self.db.get(ProjectPO, first["project_id"])
        self.assertEqual(workspace.workspace_kind, "one_off")
        self.assertEqual(workspace.llm_model, "template-model")

        workspace.llm_model = "verified-model"
        self.db.commit()
        second = service.ensure_instant_workspace()
        self.assertEqual(second["project_id"], first["project_id"])
        self.assertEqual(self.db.get(ProjectPO, first["project_id"]).llm_model, "verified-model")
        self.assertNotIn(first["project_id"], [item.id for item in ProjectRepository(self.db).get_all()])

    @patch("app.services.article_ingest_service.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))])
    def test_wechat_captcha_is_reported_as_access_restricted(self, _getaddrinfo):
        response = FakeResponse(
            url="https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?target_url=article",
            body="<html><body>环境异常，完成验证后继续访问</body></html>",
        )
        service = ArticleIngestService(self.db, FakeHTTPSession([response]))
        with patch("app.services.article_ingest_service.KNOWLEDGE_ARTICLE_URL_ENABLED", True):
            with self.assertRaises(ArticleFetchError) as raised:
                service.preview(ArticleSourcePreviewDTO(
                    project_id=self.project_id,
                    input_method="url",
                    source_url="https://mp.weixin.qq.com/s/jw7pqTwco_lLGnN_KmExig",
                ))
        self.assertEqual(raised.exception.code, "access_restricted")
        self.assertIn("粘贴文章正文", str(raised.exception))

    def test_private_network_url_is_rejected(self):
        with self.assertRaises(ArticleFetchError) as raised:
            ArticleIngestService._validate_public_url("http://127.0.0.1/admin")
        self.assertEqual(raised.exception.code, "unsafe_url")

    @patch("app.services.article_ingest_service.socket.getaddrinfo", return_value=[(None, None, None, None, ("198.18.0.121", 443))])
    def test_proxy_fake_ip_is_allowed_for_public_hostname(self, _getaddrinfo):
        ArticleIngestService._validate_public_url("https://mp.weixin.qq.com/s/example")

    def test_normalize_html_keeps_article_body_without_scripts(self):
        result = ArticleIngestService.normalize_content(
            "<html><body><script>bad()</script><article><h1>标题</h1><p>正文内容</p></article></body></html>"
        )
        self.assertIn("标题", result)
        self.assertIn("正文内容", result)
        self.assertNotIn("bad", result)

    @patch("app.services.article_ingest_service.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))])
    def test_wechat_article_root_stops_before_page_shell(self, _getaddrinfo):
        body = """
        <html><head><title>测试文章</title></head><body>
          <div id="js_content" class="rich_media_content"><h1>标题</h1><p>这是足够长的文章正文，用来验证提取器只读取文章容器内部的内容。文章还包含第二句解释，以及第三句结论，确保正文长度符合预览要求并能稳定完成解析。这里继续补充一段真实内容，验证正文结束之后的微信按钮、弹窗提示和操作文案都不会混入结果。</p></div>
          <div>预览时标签不可点</div><div>阅读原文</div><div>微信扫一扫</div><div>关注该公众号</div>
        </body></html>
        """
        service = ArticleIngestService(self.db, FakeHTTPSession([FakeResponse(body=body)]))
        with patch("app.services.article_ingest_service.KNOWLEDGE_ARTICLE_URL_ENABLED", True):
            preview = service.preview(ArticleSourcePreviewDTO(
                project_id=self.project_id,
                input_method="url",
                source_url="https://mp.weixin.qq.com/s/example",
            ))
        self.assertIn("这是足够长的文章正文", preview["normalized_content"])
        self.assertNotIn("预览时标签不可点", preview["normalized_content"])
        self.assertNotIn("阅读原文", preview["normalized_content"])
        self.assertEqual(preview["raw_content"], preview["normalized_content"])

    def test_wechat_footer_fallback_removes_ui_cluster(self):
        text = "\n".join([
            "文章标题",
            "这是一段较长的正文内容。" * 30,
            "最后一个有效结论。",
            "预览时标签不可点",
            "阅读原文",
            "微信扫一扫",
            "关注该公众号",
            "知道了",
            "赞",
            "在看",
        ])
        result = ArticleIngestService.normalize_text(text)
        self.assertIn("最后一个有效结论", result)
        self.assertNotIn("预览时标签不可点", result)
        self.assertNotIn("微信扫一扫", result)


if __name__ == "__main__":
    unittest.main()
