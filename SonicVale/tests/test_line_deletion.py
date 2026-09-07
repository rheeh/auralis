import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import soundfile as sf
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models.po import AudioAssetPO, AudioTaskPO, ChapterPO, LinePO, ProjectPO, TimelineClipPO
from app.repositories.line_repository import LineRepository
from app.services.line_service import LineService
from app.services.timeline_service import TimelineService


class LineDeletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///:memory:')
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        project = ProjectPO(name='delete-test')
        self.db.add(project); self.db.flush()
        self.chapter = ChapterPO(project_id=project.id, title='删除测试')
        self.db.add(self.chapter); self.db.flush()
        self.wav = Path(self.tmp.name) / 'original.wav'
        sf.write(self.wav, [0.1] * 16000, 16000)
        self.before = self.wav.read_bytes()
        self.line = LinePO(chapter_id=self.chapter.id, line_order=1, text_content='要删除的对白', track='voice', audio_path=str(self.wav), status='done')
        self.db.add(self.line); self.db.flush()
        self.effect = LinePO(chapter_id=self.chapter.id, line_order=2, text_content='保留的环境声', track='sfx', audio_path=str(self.wav), audio_events=[{'type': 'sound_library_placement', 'anchor_line_id': self.line.id, 'placement': 'after', 'offset_ms': 100}])
        self.db.add(self.effect)
        self.task = AudioTaskPO(id='finished-task', line_id=self.line.id, project_id=project.id, chapter_id=self.chapter.id, status='done', audio_path=str(self.wav))
        self.db.add(self.task); self.db.commit()
        self.timeline = TimelineService(self.db)
        self.timeline.build_chapter_timeline(project.id, self.chapter.id)
        self.service = LineService(LineRepository(self.db), None, None)
        self.config = patch('app.services.line_service.getConfigPath', return_value=self.tmp.name)
        self.config.start()

    def tearDown(self):
        self.config.stop(); self.db.close(); self.engine.dispose(); self.tmp.cleanup()

    def test_delete_cleans_foreign_keys_keeps_shared_audio_and_anchored_effect(self):
        line_id = self.line.id
        self.assertTrue(self.service.delete_line(line_id))
        self.assertIsNone(self.db.get(LinePO, line_id))
        self.assertEqual(self.db.query(AudioTaskPO).count(), 0)
        self.assertEqual(self.db.query(TimelineClipPO).count(), 1)
        self.assertEqual(self.db.query(AudioAssetPO).one().line_id, None)
        self.assertEqual(self.wav.read_bytes(), self.before)
        backup = json.loads(next((Path(self.tmp.name) / 'deleted_lines').glob('*.json')).read_text())
        self.assertEqual(backup['line']['id'], line_id)
        self.assertEqual(backup['tasks'][0]['audio_path'], str(self.wav))
        self.assertEqual(self.effect.line_order, 1)
        rebuilt = self.timeline.build_chapter_timeline(self.chapter.project_id, self.chapter.id, force=True)
        clip = next(clip for track in rebuilt['tracks'] for clip in track['clips'])
        self.assertEqual((rebuilt['status'], clip['start_ms']), ('ready', 1100))
        self.assertFalse(self.service.delete_line(line_id))

    def test_queued_task_prevents_deletion_without_modifying_files_or_rows(self):
        self.task.status = 'queued'; self.db.commit()
        with self.assertRaisesRegex(ValueError, '任务结束'):
            self.service.delete_line(self.line.id)
        self.assertEqual(self.db.query(LinePO).count(), 2)
        self.assertEqual(self.db.query(TimelineClipPO).count(), 2)
        self.assertEqual(self.wav.read_bytes(), self.before)
        self.assertFalse((Path(self.tmp.name) / 'deleted_lines').exists())
