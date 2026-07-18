from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from sqlalchemy.orm import Session

from app.core.config import DRAMA_WORKFLOW_MAX_SOURCE_CHARS, KNOWLEDGE_ARTICLE_URL_ENABLED
from app.dto.chat_dto import ArticleSourceImportDTO, ArticleSourcePreviewDTO
from app.models.po import ArticleSourcePO, ChatSessionPO, ProjectPO


MAX_ARTICLE_RESPONSE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5


class ArticleFetchError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _ArticleHTMLParser(HTMLParser):
    BLOCK_TAGS = {"article", "aside", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "main", "p", "pre", "section", "table", "td", "th", "tr"}
    SKIP_TAGS = {"script", "style", "svg", "noscript", "nav", "footer", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.article_parts: list[str] = []
        self.metadata: dict[str, str] = {}
        self._title_depth = 0
        self._skip_depth = 0
        self._article_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = {key.lower(): value or "" for key, value in attrs}
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag == "meta":
            key = values.get("property") or values.get("name")
            value = values.get("content")
            if key and value:
                self.metadata[key.lower()] = value.strip()
        classes = values.get("class", "").split()
        if tag in {"article", "main"} or values.get("id") == "js_content" or "rich_media_content" in classes:
            self._article_depth += 1
        if tag in self.BLOCK_TAGS:
            self._append("\n")

    def handle_endtag(self, tag: str):
        if tag in self.BLOCK_TAGS:
            self._append("\n")
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in {"article", "main"} and self._article_depth:
            self._article_depth -= 1
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        if self._title_depth:
            self.title_parts.append(data)
        self._append(data)

    def _append(self, value: str):
        self.text_parts.append(value)
        if self._article_depth:
            self.article_parts.append(value)


class ArticleIngestService:
    def __init__(self, db: Session, http_session: requests.Session | None = None):
        self.db = db
        self.http = http_session or requests.Session()

    def preview(self, dto: ArticleSourcePreviewDTO) -> dict[str, Any]:
        self._project(dto.project_id)
        if dto.input_method == "paste":
            normalized = self.normalize_text(dto.source_text or "")
            return self._preview_payload(
                input_method="paste", source_url=None, title=self._title_from_text(normalized),
                author=None, account_name=None, published_at=None,
                raw_content=dto.source_text or "", normalized_content=normalized,
            )
        if not KNOWLEDGE_ARTICLE_URL_ENABLED:
            raise ArticleFetchError("url_feature_disabled", "文章 URL 导入功能当前未启用，请粘贴正文继续")
        return self._preview_url(dto.source_url or "")

    def import_source(self, dto: ArticleSourceImportDTO) -> dict[str, Any]:
        self._project(dto.project_id)
        if not dto.rights_confirmed:
            raise ValueError("请先确认有权使用导入内容进行本地改编")
        if dto.session_id:
            session = self.db.get(ChatSessionPO, dto.session_id)
            if not session or session.project_id != dto.project_id or session.source_type != "knowledge_article":
                raise ValueError("文章会话不存在或不属于当前项目")
        normalized = self.normalize_text(dto.source_text)
        raw_content = dto.raw_content if dto.raw_content is not None else dto.source_text
        if len(raw_content.encode("utf-8")) > MAX_ARTICLE_RESPONSE_BYTES:
            raise ValueError("文章原始内容过大，请只保留需要处理的正文")
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        source = ArticleSourcePO(
            project_id=dto.project_id,
            session_id=dto.session_id,
            input_method=dto.input_method,
            source_url=(dto.source_url or "").strip() or None,
            title=(dto.title or self._title_from_text(normalized)).strip(),
            author=(dto.author or "").strip() or None,
            account_name=(dto.account_name or "").strip() or None,
            published_at=dto.published_at,
            raw_content=raw_content,
            normalized_content=normalized,
            content_hash=content_hash,
            fetch_status="ready",
            rights_confirmed=dto.rights_confirmed,
            source_metadata_json={"confirmed_chars": len(normalized)},
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return self.serialize(source, include_content=True)

    def get(self, source_id: int) -> dict[str, Any]:
        source = self.db.get(ArticleSourcePO, source_id)
        if not source:
            raise ValueError("文章来源不存在")
        return self.serialize(source, include_content=True)

    def normalize(self, source_id: int, source_text: str | None = None) -> dict[str, Any]:
        source = self.db.get(ArticleSourcePO, source_id)
        if not source:
            raise ValueError("文章来源不存在")
        source.normalized_content = self.normalize_content(source_text if source_text is not None else source.raw_content)
        source.content_hash = hashlib.sha256(source.normalized_content.encode("utf-8")).hexdigest()
        source.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(source)
        return self.serialize(source, include_content=True)

    def _preview_url(self, source_url: str) -> dict[str, Any]:
        response, final_url, body = self._fetch(source_url)
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            raise ArticleFetchError("unsupported_content_type", "链接不是可解析的 HTML 文章，请粘贴正文继续")
        parser = _ArticleHTMLParser()
        parser.feed(body)
        candidate = "".join(parser.article_parts or parser.text_parts)
        normalized = self.normalize_text(candidate)
        if len(normalized) < 80:
            raise ArticleFetchError("empty_article", "页面没有提取到有效文章正文，请粘贴正文继续")
        metadata = parser.metadata
        title = metadata.get("og:title") or "".join(parser.title_parts).strip() or self._title_from_text(normalized)
        return self._preview_payload(
            input_method="url", source_url=final_url, title=title,
            author=metadata.get("author"),
            account_name=metadata.get("og:site_name"),
            published_at=None, raw_content=body, normalized_content=normalized,
        )

    def _fetch(self, source_url: str):
        current_url = source_url.strip()
        for _ in range(MAX_REDIRECTS + 1):
            self._validate_public_url(current_url)
            try:
                response = self.http.get(
                    current_url,
                    headers={"User-Agent": "Mozilla/5.0 (Auralis Article Preview)"},
                    timeout=(5, 15),
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException as exc:
                raise ArticleFetchError("fetch_failed", f"链接访问失败：{exc}") from exc
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                if not location:
                    raise ArticleFetchError("redirect_failed", "链接重定向缺少目标地址，请粘贴正文继续")
                current_url = urljoin(current_url, location)
                continue
            if response.status_code in {401, 403}:
                raise ArticleFetchError("access_restricted", "文章需要登录或访问权限，请粘贴正文继续")
            if response.status_code >= 400:
                raise ArticleFetchError("fetch_failed", f"链接返回 HTTP {response.status_code}，请粘贴正文继续")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(65536):
                total += len(chunk)
                if total > MAX_ARTICLE_RESPONSE_BYTES:
                    raise ArticleFetchError("response_too_large", "页面内容过大，请粘贴需要处理的正文")
                chunks.append(chunk)
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            body = b"".join(chunks).decode(encoding, errors="replace")
            lowered_url = response.url.lower()
            lowered_body = body.lower()
            if "wappoc_appmsgcaptcha" in lowered_url or "wappoc_appmsgcaptcha" in lowered_body or "环境异常" in body:
                raise ArticleFetchError("access_restricted", "微信返回了访问验证页，请粘贴文章正文继续")
            return response, response.url or current_url, body
        raise ArticleFetchError("too_many_redirects", "链接重定向次数过多，请粘贴正文继续")

    @staticmethod
    def _validate_public_url(value: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ArticleFetchError("invalid_url", "请输入有效的 HTTP 或 HTTPS 文章链接")
        if parsed.username or parsed.password:
            raise ArticleFetchError("invalid_url", "文章链接不能包含用户名或密码")
        if parsed.port not in {None, 80, 443}:
            raise ArticleFetchError("invalid_url", "文章链接仅支持标准 HTTP 或 HTTPS 端口")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise ArticleFetchError("unsafe_url", "文章链接不能指向本机或内网地址")
        try:
            literal_ip = ipaddress.ip_address(hostname)
        except ValueError:
            literal_ip = None
        if literal_ip is not None and not literal_ip.is_global:
            raise ArticleFetchError("unsafe_url", "文章链接不能指向本机或内网地址")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ArticleFetchError("dns_failed", "文章链接域名无法解析") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            # macOS 上常见的本地代理会将公网域名映射到 RFC 2544 的
            # 198.18.0.0/15 fake-IP 段；仅对非 IP 域名允许该代理映射。
            proxy_fake_ip = literal_ip is None and ip in ipaddress.ip_network("198.18.0.0/15")
            if not ip.is_global and not proxy_fake_ip:
                raise ArticleFetchError("unsafe_url", "文章链接不能指向本机或内网地址")

    @staticmethod
    def normalize_text(value: str) -> str:
        text = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
        text = re.sub(r"[\t ]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            raise ValueError("文章正文不能为空")
        if len(text) > DRAMA_WORKFLOW_MAX_SOURCE_CHARS:
            raise ValueError(f"文章正文不能超过 {DRAMA_WORKFLOW_MAX_SOURCE_CHARS} 字，请选择需要处理的部分")
        return text

    @classmethod
    def normalize_content(cls, value: str) -> str:
        if re.search(r"<(?:html|body|article|main|div|p|h[1-6])\b", value, re.IGNORECASE):
            parser = _ArticleHTMLParser()
            parser.feed(value)
            value = "".join(parser.article_parts or parser.text_parts)
        return cls.normalize_text(value)

    @staticmethod
    def _title_from_text(value: str) -> str:
        return next((line.strip()[:500] for line in value.splitlines() if line.strip()), "未命名知识文章")

    @staticmethod
    def _preview_payload(**kwargs) -> dict[str, Any]:
        normalized = kwargs["normalized_content"]
        return {
            **kwargs,
            "fetch_status": "ready",
            "content_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "content_chars": len(normalized),
            "preview": normalized[:1000],
        }

    @staticmethod
    def serialize(source: ArticleSourcePO, include_content: bool = False) -> dict[str, Any]:
        data = {
            "id": source.id, "project_id": source.project_id, "session_id": source.session_id,
            "input_method": source.input_method, "source_url": source.source_url,
            "title": source.title, "author": source.author, "account_name": source.account_name,
            "published_at": source.published_at, "content_hash": source.content_hash,
            "fetch_status": source.fetch_status, "fetch_error": source.fetch_error,
            "rights_confirmed": source.rights_confirmed,
            "content_chars": len(source.normalized_content or ""),
            "created_at": source.created_at, "updated_at": source.updated_at,
        }
        if include_content:
            data.update(raw_content=source.raw_content, normalized_content=source.normalized_content)
        return data

    def _project(self, project_id: int) -> ProjectPO:
        project = self.db.get(ProjectPO, project_id)
        if not project:
            raise ValueError("项目不存在")
        return project
