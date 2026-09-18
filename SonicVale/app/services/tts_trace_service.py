from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.po import TTSGenerationPO


def redact(value, secrets=(), depth=0, *, bounded=True):
    """Store inspectable inputs, never credentials, signed URLs or audio blobs."""
    if bounded and depth > 12:
        return "[depth limit]"
    if isinstance(value, dict):
        result = {}
        for key, item in (list(value.items())[:200] if bounded else value.items()):
            name = str(key).lower()
            if re.search(r"api.?key|authorization|^auth$|secret|password|cookie|token|signature|credential|^key$", name):
                result[str(key)] = "[redacted]"
            elif name in {"audio_base64", "audio_data"} or (name in {"data", "audio"} and isinstance(item, str) and len(item) > 512):
                result[str(key)] = "[audio omitted]"
            else:
                result[str(key)] = redact(item, secrets, depth + 1, bounded=bounded)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets, depth + 1, bounded=bounded) for item in (value[:300] if bounded else value)]
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        value = re.sub(r"(?i)Bearer\s+[^\s\"',;]+", "Bearer [redacted]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", value)
        def clean_url(match):
            try:
                parts = urlsplit(match.group())
            except ValueError:
                return "[invalid URL omitted]"
            # Credentials can be embedded in the authority as well as query.
            return urlunsplit((parts.scheme, parts.netloc.split("@")[-1], parts.path, "", ""))
        value = re.sub(r"(?:https?|wss?)://[^\s\"<>]+", clean_url, value)
        return value[:24000] + ("…[truncated]" if len(value) > 24000 else "") if bounded else value
    return value if value is None or isinstance(value, (int, float, bool)) else str(type(value).__name__)


class TTSRequestRecorder:
    def __init__(self, bind, generation_id, secrets=()):
        self.Session = sessionmaker(bind=bind)
        self.generation_id = generation_id
        self.secrets = secrets

    def __call__(self, event, data):
        # Own session per callback; never pass the worker's Session to its thread.
        with self.Session() as db:
            row = db.get(TTSGenerationPO, self.generation_id)
            if not row:
                raise RuntimeError("配音生成记录不存在，已停止本次请求")
            if event == "request":
                row.request_json = redact(data, self.secrets)
                if row.status == "preparing":
                    row.status = "requesting"
            elif event == "response":
                row.response_json = redact(data, self.secrets)
            elif event == "prepared":
                row.input_snapshot = redact(data, self.secrets)
            db.commit()


class TTSTraceService:
    def __init__(self, db):
        self.db = db

    def begin(self, project_id, chapter_id, line_id, task_id=None, input_snapshot=None):
        row = TTSGenerationPO(id=uuid4().hex, project_id=project_id, chapter_id=chapter_id,
                              line_id=line_id, task_id=task_id, input_snapshot=redact(input_snapshot))
        self.db.add(row)
        self.db.commit()
        return row.id

    def finish(self, generation_id, *, audio=None, version_id=None, error=None, secrets=()):
        row = self.db.get(TTSGenerationPO, generation_id)
        if not row:
            return
        row.status = "failed" if error else "succeeded"
        row.audio_version_id = version_id
        row.error_message = redact(str(error), secrets) if error else None
        row.result_json = redact(audio, secrets) if audio is not None else None
        row.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def list(self, project_id, line_id=None, limit=30, before=None):
        query = select(TTSGenerationPO).where(TTSGenerationPO.project_id == project_id)
        if line_id is not None:
            query = query.where(TTSGenerationPO.line_id == line_id)
        if before:
            cursor = self.db.get(TTSGenerationPO, before)
            if not cursor or cursor.project_id != project_id or (line_id is not None and cursor.line_id != line_id):
                raise ValueError("无效的记录分页位置")
            from sqlalchemy import or_, and_
            query = query.where(or_(TTSGenerationPO.created_at < cursor.created_at,
                and_(TTSGenerationPO.created_at == cursor.created_at, TTSGenerationPO.id < cursor.id)))
        rows = list(self.db.scalars(query.order_by(TTSGenerationPO.created_at.desc(), TTSGenerationPO.id.desc()).limit(limit + 1)))
        return {"items": [self.serialize(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None}

    @staticmethod
    def serialize(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
