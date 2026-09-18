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
            AudioTaskPO.line_id == line_id, AudioTaskPO.status.in_(['queued', 'processing', 'completing'])
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
        # Preserve every historical take in the version picker, detached from the
        # new input. Type changes share the normal command's transaction/invalidations.
        versions=list(line.audio_versions or [])
        if line.audio_path and Path(line.audio_path).is_file() and not any(v.get('audio_path')==line.audio_path for v in versions):
            versions.append({'id':uuid4().hex,'audio_path':line.audio_path,'kind':'generated',
                'origin':'before_type_change','text':line.text_content,'stale':True})
        output_dir = Path(getConfigPath()) / 'assets' / str(line.chapter_id) / 'audio'
        output_dir.mkdir(parents=True, exist_ok=True)
        changes={'track':dto.track,'line_type':'dialogue' if dto.track=='voice' else dto.track,
            'should_speak':int(spoken),'role_id':role.id if spoken else None,'voice_id':None,
            'text_content':text,'production_note':dto.production_note.strip() or None,
            'sound_prompt':None if spoken else text,'sound_tags':[] if spoken else infer_tags(text),
            'voice_profile':None,'audio_path':str(output_dir/f'id_{line.id}_type_{uuid4().hex[:12]}.wav') if spoken else None,
            'subtitle_path':None,'audio_events':[],'audio_versions':versions,
            'active_audio_version_id':None,'active_audio_variant_id':None,'status':'pending','is_done':0}
        if not spoken:changes.update(emotion_id=None,strength_id=None)
        from app.services.factory import get_line_service
        get_line_service(self.db).update_line(line.id,changes)
        return {'line_id': line.id, 'track': line.track, 'role_id': line.role_id, 'needs_generation': spoken, 'history_file': backup.name}
