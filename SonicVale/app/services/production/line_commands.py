"""Authoritative short transactions for line edits; no transport or provider I/O."""
from sqlalchemy import select
from app.core.sound_tags import infer_tags
from app.models.po import ChapterPO, LinePO, RolePO, VoicePO
from app.services.timeline_service import TimelineService

GENERATION_FIELDS = {'text_content','production_note','emotion_id','strength_id','voice_id',
                     'role_id','line_type','track','should_speak','line_order','scene_title','voice_profile'}
ASSET_FIELDS = {'audio_path','active_audio_version_id','active_audio_variant_id','audio_events','sound_prompt','sound_tags'}


class LineCommands:
    def __init__(self, repository):
        self.repository = repository
        self.db = repository.db

    def update(self, line_id, data, *, commit=True):
        line = self.repository.get_by_id(line_id)
        if not line:
            return False
        data = dict(data)
        if 'chapter_id' in data and data['chapter_id'] != line.chapter_id:
            raise ValueError('不能通过台词修改移动章节')
        chapter = self.db.get(ChapterPO, line.chapter_id)
        if data.get('role_id') is not None:
            role = self.db.get(RolePO, data['role_id'])
            if not chapter or not role or role.project_id != chapter.project_id:
                raise ValueError('角色不属于当前项目')
        if data.get('voice_id') is not None and not self.db.get(VoicePO,data['voice_id']):
            raise ValueError('音色不存在')
        if line.track in {'sfx','bgm'} and 'sound_tags' not in data and any(k in data for k in ('sound_prompt','text_content')):
            data['sound_tags'] = infer_tags(data.get('sound_prompt') or data.get('text_content') or line.sound_prompt)
        changed = {key for key,value in data.items() if value != getattr(line,key,None)}
        try:
            if changed & GENERATION_FIELDS:
                # Scene context/continuity can affect neighbours: invalidate this
                # scene conservatively, retaining all files and user selections.
                neighbours = self.db.scalars(select(LinePO).where(LinePO.chapter_id == line.chapter_id,
                    LinePO.scene_title == line.scene_title)).all()
                for neighbour in neighbours:
                    if neighbour.should_speak != 0 and neighbour.track not in {'sfx','bgm'}:
                        neighbour.status, neighbour.is_done = 'pending', 0
                if data.get('should_speak',line.should_speak)!=0 and data.get('track',line.track) not in {'sfx','bgm'}:
                    data.update(status='pending', is_done=0)
            self.repository.update(line_id, data, commit=False)
            if changed & (GENERATION_FIELDS | ASSET_FIELDS):
                TimelineService.invalidate_line(self.db,line_id,commit=False)
            if commit:self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def clear_role(self, role_id, *, commit=True):
        try:
            for line in self.repository.get_lines_by_role_id(role_id):
                self.update(line.id,{'role_id':None},commit=False)
            if commit:self.db.commit()
        except Exception:
            self.db.rollback();raise

    def reorder(self, orders):
        ids = [item.id for item in orders]
        rows = [self.repository.get_by_id(id) for id in ids]
        if len(ids) != len(set(ids)) or any(row is None for row in rows) or len({r.chapter_id for r in rows}) > 1:
            raise ValueError('排序必须是同一章节中的不同台词')
        if any(item.line_order < 1 for item in orders) or len({i.line_order for i in orders}) != len(orders):
            raise ValueError('排序位置必须为不同的正整数')
        try:
            for row,item in zip(rows,orders):
                if row.line_order != item.line_order:
                    row.line_order = item.line_order
                    row.status,row.is_done = 'pending',0
                    TimelineService.invalidate_line(self.db,row.id,commit=False)
            self.db.commit()
        except Exception:
            self.db.rollback(); raise
        return True
