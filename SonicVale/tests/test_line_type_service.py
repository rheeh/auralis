import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.line_dto import LineTypeChangeDTO
from app.models.po import AudioTaskPO, ChapterPO, LinePO, ProjectPO, RolePO
from app.services.line_type_service import LineTypeService
from app.workflows.drama.schemas import ScriptLine


class LineTypeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AURALIS_CONFIG_DIR': self.tmp.name})
        self.env.start()
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        project = ProjectPO(name='type-test')
        self.db.add(project); self.db.flush()
        self.chapter = ChapterPO(project_id=project.id, title='雨夜')
        self.role = RolePO(project_id=project.id, name='林晚')
        self.db.add_all([self.chapter, self.role]); self.db.flush()
        self.old = Path(self.tmp.name) / 'original.wav'
        self.old.write_bytes(b'original audio must remain unchanged')
        self.line = LinePO(chapter_id=self.chapter.id, line_order=1, track='sfx', line_type='sfx', should_speak=0, text_content='林晚轻笑', audio_path=str(self.old), status='done', is_done=1, sound_tags=['笑声'])
        self.db.add(self.line); self.db.commit()
        self.service = LineTypeService(self.db)

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.env.stop(); self.tmp.cleanup()

    def dto(self, **changes):
        return LineTypeChangeDTO(**{'chapter_id': self.chapter.id, 'track': 'voice', 'role_id': self.role.id, 'text_content': '呵。', 'production_note': '自然轻笑', **changes})

    def test_conversion_routes_to_character_and_preserves_old_take(self):
        self.service.change(self.line.id, self.dto())
        self.assertEqual((self.line.track, self.line.line_type, self.line.should_speak, self.line.role_id), ('voice', 'dialogue', 1, self.role.id))
        self.assertEqual(self.line.status, 'pending')
        self.assertFalse(Path(self.line.audio_path).exists())
        self.assertNotEqual(self.line.audio_path, str(self.old))
        self.assertEqual(self.old.read_bytes(), b'original audio must remain unchanged')
        history = list((Path(self.tmp.name) / 'line_type_history').glob('*.json'))
        self.assertEqual(json.loads(history[0].read_text())['audio_path'], str(self.old))
        self.service.change(self.line.id, self.dto(track='bgm', role_id=None, text_content='平静钢琴'))
        self.assertEqual((self.line.track, self.line.should_speak, self.line.role_id, self.line.audio_path), ('bgm', 0, None, None))
        self.assertEqual(self.line.sound_prompt, '平静钢琴')

    def test_invalid_role_wrong_chapter_and_busy_task_leave_line_untouched(self):
        effect_role = RolePO(project_id=self.role.project_id, name='音效')
        self.db.add(effect_role); self.db.commit()
        with self.assertRaises(ValueError): self.service.change(self.line.id, self.dto(role_id=effect_role.id))
        for dto in [self.dto(role_id=None), self.dto(role_id=999), self.dto(chapter_id=999), self.dto(text_content='（轻笑）')]:
            with self.assertRaises(ValueError): self.service.change(self.line.id, dto)
        self.db.add(AudioTaskPO(id='busy', project_id=self.role.project_id, chapter_id=self.chapter.id, line_id=self.line.id, status='queued'))
        self.db.commit()
        with self.assertRaises(ValueError): self.service.change(self.line.id, self.dto())
        self.assertEqual(self.line.track, 'sfx')
        self.assertEqual(self.line.audio_path, str(self.old))
        self.assertFalse((Path(self.tmp.name) / 'line_type_history').exists())

    def test_actor_laugh_stays_in_voice_but_crowd_remains_effect(self):
        line = ScriptLine(type='dialogue', speaker='林晚', text='（轻笑）你又来了。')
        self.assertEqual(line.text, '你又来了。')
        self.assertIn('轻笑', line.productionNote)
        self.assertEqual(line.audioEvents, [])
        laugh = ScriptLine(type='dialogue', speaker='林晚', text='（轻笑）')
        self.assertEqual((laugh.text, laugh.track, laugh.speaker), ('呵。', 'voice', '林晚'))
        crowd = ScriptLine(type='dialogue', speaker='林晚', text='开始吧。（观众大笑）')
        self.assertEqual(crowd.audioEvents[0].type, 'sfx')
        self.assertEqual(crowd.audioEvents[0].content, '观众大笑')
