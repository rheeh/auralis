import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.migrations import apply_schema_migrations
from app.dto.timeline_dto import TimelineClipUpdateDTO
from app.dto.sound_library_dto import SoundLibraryInsertDTO
from app.models.po import ChapterPO, LinePO, ProjectPO, TimelineClipPO
from app.services.timeline_render_service import TimelineRenderService
from app.services.timeline_service import TimelineService
from app.services.sound_library_service import SoundLibraryService


class TimelineRenderServiceTest(unittest.TestCase):
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
        self.project = ProjectPO(name="Timeline render", project_root_path=self.temp_dir.name)
        self.session.add(self.project)
        self.session.flush()
        self.chapter = ChapterPO(project_id=self.project.id, title="混音测试")
        self.session.add(self.chapter)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _tone(self, name: str, value: float, seconds: float) -> str:
        path = os.path.join(self.temp_dir.name, name)
        sf.write(path, np.full(round(seconds * 16000), value, dtype=np.float32), 16000)
        return path

    def _build_three_clip_timeline(self):
        voice = LinePO(
            chapter_id=self.chapter.id,
            line_order=1,
            text_content="对白",
            track="voice",
            audio_path=self._tone("voice.wav", 0.1, 1.0),
            status="done",
            is_done=1,
        )
        sfx = LinePO(
            chapter_id=self.chapter.id,
            line_order=2,
            text_content="音效",
            track="sfx",
            line_type="sfx",
            should_speak=0,
            audio_path=self._tone("sfx.wav", 0.2, 0.5),
            status="done",
            is_done=1,
        )
        muted = LinePO(
            chapter_id=self.chapter.id,
            line_order=3,
            text_content="静音片段",
            track="bgm",
            line_type="bgm",
            should_speak=0,
            audio_path=self._tone("muted.wav", 0.5, 1.0),
            status="done",
            is_done=1,
        )
        self.session.add_all([voice, sfx, muted])
        self.session.commit()
        TimelineService(self.session).build_chapter_timeline(self.project.id, self.chapter.id)
        clips = {clip.track_type: clip for clip in self.session.query(TimelineClipPO).all()}
        timeline = TimelineService(self.session)
        timeline.update_clip(
            self.project.id,
            self.chapter.id,
            clips["sfx"].id,
            TimelineClipUpdateDTO(start_ms=500, volume_db=-6, fade_in_ms=200),
        )
        timeline.update_clip(
            self.project.id,
            self.chapter.id,
            clips["bgm"].id,
            TimelineClipUpdateDTO(start_ms=0, is_muted=True),
        )
        return clips

    def test_render_uses_start_volume_fade_and_muted_state(self):
        clips = self._build_three_clip_timeline()
        service = TimelineRenderService(self.session)

        result = service.render_chapter(self.project.id, self.chapter.id)

        self.assertTrue(os.path.isfile(result["audio_path"]))
        self.assertTrue(os.path.isfile(result["manifest_path"]))
        self.assertEqual(result["clip_count"], 3)
        self.assertEqual(result["rendered_clip_count"], 2)
        self.assertEqual(result["muted_clip_count"], 1)
        audio, sample_rate = sf.read(result["audio_path"], dtype="float32", always_2d=True)
        self.assertEqual(sample_rate, 44100)
        self.assertEqual(audio.shape[1], 2)
        self.assertAlmostEqual(len(audio) / sample_rate, 1.0, delta=0.02)
        self.assertAlmostEqual(float(audio[round(0.25 * sample_rate), 0]), 0.1, delta=0.015)
        self.assertAlmostEqual(float(audio[round(0.51 * sample_rate), 0]), 0.105, delta=0.025)
        self.assertAlmostEqual(float(audio[round(0.75 * sample_rate), 0]), 0.2, delta=0.025)

        with open(result["manifest_path"], encoding="utf-8") as stream:
            manifest = json.load(stream)
        self.assertEqual(manifest["render_engine"], "ffmpeg_timeline_mix_v1")
        self.assertEqual(manifest["duration_ms"], 1000)
        sfx = next(item for item in manifest["clips"] if item["id"] == clips["sfx"].id)
        self.assertEqual(sfx["start_ms"], 500)
        self.assertEqual(sfx["fade_in_ms"], 200)
        self.assertEqual(sfx["volume_db"], -6)

        latest = service.get_latest_render(self.project.id, self.chapter.id)
        self.assertEqual(latest["render_fingerprint"], result["render_fingerprint"])

    def test_quick_added_sound_is_audible_at_anchor_with_requested_gain(self):
        voice = LinePO(
            chapter_id=self.chapter.id, line_order=1, text_content="门外是谁？", track="voice",
            audio_path=self._tone("dialogue.wav", 0.1, 1.0), status="done", is_done=1,
        )
        self.session.add(voice)
        self.session.commit()
        library = SoundLibraryService(self.session)
        with patch("app.services.sound_library_service.getConfigPath", return_value=self.temp_dir.name):
            asset = library.import_path(self._tone("door.wav", 0.2, 0.5), "门锁响动", "doors")
            added = library.insert_asset(asset["id"], SoundLibraryInsertDTO(
                chapter_id=self.chapter.id, anchor_line_id=voice.id,
                placement="with", offset_ms=500, volume_db=-6,
            ))
        self.assertTrue(added["placement_pending"])
        TimelineService(self.session).build_chapter_timeline(self.project.id, self.chapter.id)
        result = TimelineRenderService(self.session).render_chapter(self.project.id, self.chapter.id)
        audio, sample_rate = sf.read(result["audio_path"], dtype="float32", always_2d=True)
        self.assertAlmostEqual(len(audio) / sample_rate, 1.0, delta=0.02)
        self.assertAlmostEqual(float(audio[round(0.25 * sample_rate), 0]), 0.1, delta=0.015)
        self.assertAlmostEqual(float(audio[round(0.75 * sample_rate), 0]), 0.2, delta=0.025)

    def test_edit_invalidates_previous_render_and_stale_timeline_is_rejected(self):
        clips = self._build_three_clip_timeline()
        service = TimelineRenderService(self.session)
        service.render_chapter(self.project.id, self.chapter.id)

        TimelineService(self.session).update_clip(
            self.project.id,
            self.chapter.id,
            clips["voice"].id,
            TimelineClipUpdateDTO(volume_db=-3),
        )
        with self.assertRaisesRegex(ValueError, "旧成片已过期"):
            service.get_latest_render(self.project.id, self.chapter.id)

        TimelineService.invalidate_line(self.session, clips["voice"].line_id, "源音频已变化")
        with self.assertRaisesRegex(ValueError, "时间线状态为 stale"):
            service.render_chapter(self.project.id, self.chapter.id)

    def test_clip_edit_rejects_invalid_duration_and_fades(self):
        clips = self._build_three_clip_timeline()
        service = TimelineService(self.session)
        with self.assertRaisesRegex(ValueError, "不能超过源音频时长"):
            service.update_clip(
                self.project.id,
                self.chapter.id,
                clips["sfx"].id,
                TimelineClipUpdateDTO(duration_ms=900),
            )
        with self.assertRaisesRegex(ValueError, "总时长不能超过"):
            service.update_clip(
                self.project.id,
                self.chapter.id,
                clips["sfx"].id,
                TimelineClipUpdateDTO(fade_in_ms=300, fade_out_ms=300),
            )


if __name__ == "__main__":
    unittest.main()
