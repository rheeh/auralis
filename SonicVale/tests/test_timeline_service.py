import os
import tempfile
import unittest

import soundfile as sf
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.migrations import apply_schema_migrations
from app.models.po import AudioAssetPO, ChapterPO, LinePO, ProjectPO, TimelineClipPO, TimelineTrackPO
from app.services.timeline_service import TimelineService


class TimelineServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
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
        self.assertEqual(payload["status"], "ready")
        self.assertEqual({track["status"] for track in payload["tracks"]}, {"ready"})
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
            self.assertEqual(conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one(), 4)
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
            self.assertIn("project_root_path", columns)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM audio_assets")).scalar_one(), 0)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM sound_library_assets")).scalar_one(), 0)
        engine.dispose()

    def test_invalidation_marks_stale_and_manual_clips_are_protected(self):
        project = ProjectPO(name="Lifecycle timeline")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="第一场")
        self.session.add(chapter)
        self.session.flush()
        path = self._wav("lifecycle.wav", 1.0)
        line = LinePO(chapter_id=chapter.id, line_order=1, track="voice", audio_path=path)
        self.session.add(line)
        self.session.commit()
        service = TimelineService(self.session)
        service.build_chapter_timeline(project.id, chapter.id)

        service.invalidate_line(self.session, line.id)
        self.assertEqual(service.get_chapter_timeline(project.id, chapter.id)["status"], "stale")

        clip = self.session.query(TimelineClipPO).one()
        clip.is_user_edited = True
        self.session.commit()
        protected = service.build_chapter_timeline(project.id, chapter.id, force=True)
        self.assertEqual(protected["status"], "stale")
        self.assertEqual(self.session.query(TimelineClipPO).count(), 1)

    def test_clear_chapter_removes_tracks_clips_and_assets(self):
        project = ProjectPO(name="Cleanup timeline")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="第一场")
        self.session.add(chapter)
        self.session.flush()
        path = self._wav("cleanup.wav", 1.0)
        self.session.add(LinePO(chapter_id=chapter.id, line_order=1, track="voice", audio_path=path))
        self.session.commit()
        service = TimelineService(self.session)
        service.build_chapter_timeline(project.id, chapter.id)
        self.assertEqual(self.session.query(TimelineTrackPO).count(), 4)
        service.clear_chapter_timeline(self.session, chapter.id)
        self.session.commit()
        self.assertEqual(self.session.query(TimelineTrackPO).count(), 0)
        self.assertEqual(self.session.query(TimelineClipPO).count(), 0)
        self.assertEqual(self.session.query(AudioAssetPO).count(), 0)

    def test_shared_asset_survives_first_chapter_cleanup_and_is_collected_after_last_reference(self):
        project = ProjectPO(name="Shared asset timeline")
        self.session.add(project)
        self.session.flush()
        chapter_one = ChapterPO(project_id=project.id, title="第一场")
        chapter_two = ChapterPO(project_id=project.id, title="第二场")
        self.session.add_all([chapter_one, chapter_two])
        self.session.flush()
        shared_path = self._wav("shared-bgm.wav", 0.5)
        line_one = LinePO(chapter_id=chapter_one.id, line_order=1, track="bgm", line_type="bgm", should_speak=0, audio_path=shared_path)
        line_two = LinePO(chapter_id=chapter_two.id, line_order=1, track="bgm", line_type="bgm", should_speak=0, audio_path=shared_path)
        self.session.add_all([line_one, line_two])
        self.session.commit()
        service = TimelineService(self.session)
        service.build_chapter_timeline(project.id, chapter_one.id)
        service.build_chapter_timeline(project.id, chapter_two.id)
        self.assertEqual(self.session.query(AudioAssetPO).count(), 1)
        self.assertEqual(self.session.query(TimelineClipPO).count(), 2)

        service.clear_line_timeline(self.session, line_one.id)
        self.session.commit()
        self.assertEqual(self.session.query(AudioAssetPO).count(), 1)
        self.assertEqual(self.session.query(TimelineClipPO).count(), 1)

        service.clear_chapter_timeline(self.session, chapter_two.id)
        self.session.commit()
        self.assertEqual(self.session.query(AudioAssetPO).count(), 0)
        self.assertEqual(self.session.query(TimelineClipPO).count(), 0)

    def test_sqlite_foreign_keys_are_enabled_for_lifecycle_operations(self):
        self.assertEqual(self.session.execute(text("PRAGMA foreign_keys")).scalar_one(), 1)

    def test_switching_selected_audio_version_rebuilds_the_clip_asset(self):
        project = ProjectPO(name="Version switch timeline")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="第一场")
        self.session.add(chapter)
        self.session.flush()
        old_path = self._wav("old-take.wav", 0.4)
        new_path = self._wav("new-take.wav", 0.9)
        line = LinePO(
            chapter_id=chapter.id,
            line_order=1,
            track="voice",
            audio_path=old_path,
            audio_versions=[{"id": "v2", "audio_path": new_path}],
            active_audio_version_id="v2",
        )
        self.session.add(line)
        self.session.commit()
        service = TimelineService(self.session)
        first = service.build_chapter_timeline(project.id, chapter.id)
        first_clip = next(clip for track in first["tracks"] for clip in track["clips"])
        self.assertEqual(first_clip["asset"]["path"], os.path.abspath(new_path))

        line.active_audio_version_id = None
        self.session.commit()
        service.invalidate_line(self.session, line.id, "切换当前音频版本")
        rebuilt = service.build_chapter_timeline(project.id, chapter.id, force=True)
        rebuilt_clip = next(clip for track in rebuilt["tracks"] for clip in track["clips"])
        self.assertEqual(rebuilt_clip["asset"]["path"], os.path.abspath(old_path))
        self.assertEqual(rebuilt_clip["duration_ms"], 400)


if __name__ == "__main__":
    unittest.main()
