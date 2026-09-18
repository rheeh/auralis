"""Chapter replacement/deletion preparation. Caller owns commit/rollback."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, delete, update
from app.core.config import getConfigPath
from app.models.po import (ChapterPO, LinePO, AudioTaskPO, AudioAssetPO,
                           TimelineTrackPO, TimelineClipPO, ChatSessionPO, SourceDocumentPO, TTSGenerationPO)
from app.services.timeline_service import TimelineService


def chapter_snapshot(db, chapter_id):
    def row(item):
        return {c.name:getattr(item,c.name) for c in item.__table__.columns}
    chapter = db.get(ChapterPO,chapter_id)
    if not chapter:
        raise ValueError('章节不存在')
    result = {'chapter':row(chapter)}
    for model in (LinePO, AudioTaskPO, AudioAssetPO, TimelineTrackPO, TimelineClipPO, ChatSessionPO, TTSGenerationPO):
        result[model.__tablename__] = [row(item) for item in db.scalars(select(model).where(model.chapter_id==chapter_id).order_by(model.id))]
    document_ids = [s['source_document_id'] for s in result['chat_sessions'] if s.get('source_document_id')]
    result['source_documents'] = [row(item) for item in db.scalars(select(SourceDocumentPO).where(SourceDocumentPO.id.in_(document_ids)))]
    return result


def chapter_version(db, chapter_id):
    snapshot = chapter_snapshot(db,chapter_id)
    # Leases and task progress do not change the editable production revision.
    content = {k:snapshot[k] for k in ('chapter','lines','timeline_tracks','timeline_clips')}
    return hashlib.sha256(json.dumps(content,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def prepare_removal(db, chapter_id):
    if db.scalar(select(AudioTaskPO.id).where(AudioTaskPO.chapter_id==chapter_id,
            AudioTaskPO.status.in_(['queued','processing','completing'])).limit(1)):
        raise ValueError('章节仍有活动配音任务')
    snapshot = chapter_snapshot(db,chapter_id)
    directory = Path(getConfigPath()) / 'chapter_history'
    directory.mkdir(parents=True,exist_ok=True)
    (directory/f'{chapter_id}-{uuid4().hex}.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    TimelineService.clear_chapter_timeline(db,chapter_id)
    ids = select(LinePO.id).where(LinePO.chapter_id==chapter_id)
    db.execute(update(AudioAssetPO).where(AudioAssetPO.line_id.in_(ids)).values(line_id=None))
    db.execute(delete(AudioTaskPO).where(AudioTaskPO.line_id.in_(ids)))
    db.execute(delete(LinePO).where(LinePO.chapter_id==chapter_id))
