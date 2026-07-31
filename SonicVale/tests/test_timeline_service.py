import os
import tempfile
import unittest

import soundfile as sf
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.migrations import apply_schema_migrations
from app.models.po import AudioAssetPO, ChapterPO, LinePO, ProjectPO
from app.services.timeline_service import TimelineService


class TimelineServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        apply_schema_migrations(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _wav(self, name: str, seconds: float) -> str:
        path = os.path.join(self.temp_dir.name, name)
        frames = max(1, round(seconds * 16000))
        sf.write(path, [0.0] * frames, 16000)
        return path

    def test_build_uses_real_audio_duration_and_registers_four_tracks(self):
        project = ProjectPO(name="Timeline project")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="第一场", text_content="测试")
        self.session.add(chapter)
        self.session.flush()

        voice_path = self._wav("voice.wav", 1.25)
        narration_path = self._wav("narration.wav", 2.5)
        sfx_path = self._wav("door.wav", 0.75)
        self.session.add_all([
            LinePO(chapter_id=chapter.id, line_order=1, text_content="人物", track="voice", audio_path=voice_path, status="done", is_done=1),
            LinePO(chapter_id=chapter.id, line_order=2, text_content="旁白", track="narration", audio_path=narration_path, status="done", is_done=1),
            LinePO(chapter_id=chapter.id, line_order=3, text_content="关门", track="sfx", should_speak=0, audio_path=sfx_path, status="done", is_done=1),
        ])
        self.session.commit()

        payload = TimelineService(self.session).build_chapter_timeline(project.id, chapter.id)

        self.assertEqual(payload["track_count"], 4)
        self.assertEqual(payload["clip_count"], 3)
        clips = [clip for track in payload["tracks"] for clip in track["clips"]]
        self.assertEqual(sorted(clip["duration_ms"] for clip in clips), [750, 1250, 2500])
        self.assertEqual(sorted(clip["start_ms"] for clip in clips), [0, 1250, 3750])
        self.assertEqual(self.session.query(AudioAssetPO).count(), 3)

    def test_build_is_idempotent_without_force(self):
        project = ProjectPO(name="Idempotent timeline")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="第一场")
        self.session.add(chapter)
        self.session.flush()
        path = self._wav("line.wav", 1.0)
        self.session.add(LinePO(chapter_id=chapter.id, line_order=1, track="voice", audio_path=path))
        self.session.commit()
        service = TimelineService(self.session)
        first = service.build_chapter_timeline(project.id, chapter.id)
        second = service.build_chapter_timeline(project.id, chapter.id)
        self.assertEqual(first["clip_count"], second["clip_count"])
        self.assertEqual(self.session.execute(text("SELECT COUNT(*) FROM timeline_clips")).scalar_one(), 1)

    def test_legacy_sqlite_data_survives_versioned_migration(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
            conn.execute(text("CREATE TABLE lines (id INTEGER PRIMARY KEY, chapter_id INTEGER NOT NULL)"))
            conn.execute(text("INSERT INTO projects (id, name) VALUES (7, '旧项目')"))

        apply_schema_migrations(engine)

        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT name FROM projects WHERE id = 7")).scalar_one(), "旧项目")
            self.assertEqual(conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one(), 2)
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
            self.assertIn("project_root_path", columns)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM audio_assets")).scalar_one(), 0)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
