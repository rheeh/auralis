"""Explicit, non-destructive corrections to a committed script's track and speaker."""
import json
from pathlib import Path
from uuid import uuid4

from app.core.config import getConfigPath
from app.core.sound_tags import infer_tags
from app.models.po import AudioTaskPO, ChapterPO, LinePO, RolePO
from app.services.timeline_service import TimelineService


class LineTypeService:
    def __init__(self, db):
        self.db = db

    def change(self, line_id, dto):
        line = self.db.get(LinePO, line_id)
        if not line or line.chapter_id != dto.chapter_id:
            raise ValueError('请选择当前章节中的台词')
        if line.status == 'processing' or self.db.query(AudioTaskPO).filter(
            AudioTaskPO.line_id == line_id, AudioTaskPO.status.in_(['queued', 'processing'])
        ).first():
            raise ValueError('本句正在等待或生成音频，请任务结束后再修改类型')
        chapter = self.db.get(ChapterPO, line.chapter_id)
        spoken = dto.track in {'voice', 'narration'}
        role = self.db.get(RolePO, dto.role_id) if dto.role_id else None
        if spoken and (not chapter or not role or role.project_id != chapter.project_id or role.name in {'音效', 'BGM', '背景音乐', '环境音'}):
            raise ValueError('请为人物台词或旁白选择当前项目中的角色')
        text = dto.text_content.strip()
        if not text:
            raise ValueError('请填写台词文本或声音描述')
        if spoken and any(c in text for c in '()（）[]【】'):
            raise ValueError('请把括号内的表演说明放到声音指导，朗读文本只保留实际发声内容')
        # Preserve full metadata and all historical file references before detaching
        # the previous take. Conversion never deletes or rewrites audio files.
        history = Path(getConfigPath()) / 'line_type_history'
        history.mkdir(parents=True, exist_ok=True)
        snapshot = {column.name: getattr(line, column.name) for column in LinePO.__table__.columns}
        backup = history / f'{line_id}-{uuid4().hex}.json'
        backup.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
        line.track = dto.track
        line.line_type = 'dialogue' if dto.track == 'voice' else dto.track
        line.should_speak = int(spoken)
        line.role_id = role.id if spoken else None
        line.voice_id = None  # inherit the selected character's current voice
        line.text_content = text
        line.production_note = dto.production_note.strip() or None
        line.sound_prompt = None if spoken else text
        line.sound_tags = [] if spoken else infer_tags(text)
        line.voice_profile = None
        output_dir = Path(getConfigPath()) / 'assets' / str(line.chapter_id) / 'audio'
        output_dir.mkdir(parents=True, exist_ok=True)
        line.audio_path = str(output_dir / f'id_{line.id}_type_{uuid4().hex[:12]}.wav') if spoken else None
        line.subtitle_path = None
        line.audio_events = []
        line.audio_versions = []
        line.audio_variants = []
        line.active_audio_version_id = None
        line.active_audio_variant_id = None
        line.status = 'pending'
        line.is_done = 0
        if not spoken:
            line.emotion_id = None
            line.strength_id = None
        self.db.commit()
        TimelineService.invalidate_line(self.db, line.id, '台词类型或角色已修改，请重新生成素材并刷新编排')
        return {'line_id': line.id, 'track': line.track, 'role_id': line.role_id, 'needs_generation': spoken, 'history_file': backup.name}
