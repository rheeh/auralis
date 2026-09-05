import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import soundfile as sf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.migrations import apply_schema_migrations
from app.dto.sound_library_dto import SoundLibraryInsertDTO
from app.dto.timeline_dto import TimelineClipUpdateDTO
from app.models.po import ChapterPO, LinePO, ProjectPO, SoundLibraryAssetPO, TimelineClipPO
from app.services.sound_library_service import SoundLibraryService
from app.services.timeline_service import TimelineService
from app.services.line_service import LineService
from app.repositories.line_repository import LineRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.repositories.llm_provider_repository import LLMProviderRepository


class SoundLibraryServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        apply_schema_migrations(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = tempfile.TemporaryDirectory()
        builtin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "audio", "cc0"))
        self.service = SoundLibraryService(self.session, builtin_root=builtin_root)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()
        self.config_dir.cleanup()

    def _wav(self, name="custom.wav"):
        path = os.path.join(self.temp_dir.name, name)
        sf.write(path, [0.0] * 8000, 16000)
        return path

    def test_builtin_catalog_is_complete_and_filterable(self):
        assets = self.service.list_assets(source_type="builtin")
        self.assertEqual(len(assets), 32)
        self.assertTrue(all(asset["license"] == "CC0-1.0" for asset in assets))
        self.assertTrue(all(asset["duration_ms"] > 0 for asset in assets))
        self.assertTrue(all(os.path.isfile(asset["path"]) for asset in assets))
        weather = self.service.list_assets(source_type="builtin", category="weather")
        self.assertEqual({asset["category"] for asset in weather}, {"weather"})
        self.assertTrue(self.service.list_assets(source_type="builtin", keyword="thunder"))
        self.assertEqual(
            [asset["name"] for asset in self.service.list_assets(source_type="builtin", keyword="火焰")],
            ["火焰燃烧"],
        )

    def test_compressed_metadata_does_not_load_native_mpeg_decoder(self):
        mp3 = next(Path(self.service.builtin_root).rglob('*.mp3'))
        with patch('app.core.audio_metadata.sf.info', side_effect=AssertionError('MP3 must be isolated')):
            duration, rate, channels = self.service._audio_info(mp3)
        self.assertGreater(duration, 0)
        self.assertGreater(rate, 0)
        self.assertIn(channels, (1, 2))

    def test_reselecting_sound_keeps_prior_audio_file(self):
        _, chapter, _, asset = self._chapter()
        original = self._wav('original-effect.wav')
        line = LinePO(chapter_id=chapter.id, line_order=4, track='sfx', line_type='sfx', audio_path=original)
        self.session.add(line)
        self.session.commit()
        service = LineService(LineRepository(self.session), RoleRepository(self.session), TTSProviderRepository(self.session), LLMProviderRepository(self.session))
        original_bytes = Path(original).read_bytes()
        first = service.attach_audio_asset(line.id, asset['path'])
        first_bytes = Path(first).read_bytes()
        second = service.attach_audio_asset(line.id, asset['path'])
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), first_bytes)
        self.assertEqual(Path(original).read_bytes(), original_bytes)
        self.assertEqual(self.session.get(LinePO, line.id).audio_path, second)

    def test_binding_sound_updates_only_target_clip_and_keeps_manual_mix(self):
        project, chapter, lines, asset = self._chapter()
        effect = LinePO(chapter_id=chapter.id, line_order=4, track='sfx', line_type='sfx', audio_path=self._wav('previous.wav'))
        self.session.add(effect)
        self.session.commit()
        timeline = TimelineService(self.session)
        built = timeline.build_chapter_timeline(project.id, chapter.id)
        target = next(t for t in built['tracks'] if t['track_type'] == 'sfx')['clips'][0]
        timeline.update_clip(project.id, chapter.id, target['id'], TimelineClipUpdateDTO(start_ms=230, volume_db=-18, fade_in_ms=20, fade_out_ms=40))
        before = timeline.get_chapter_timeline(project.id, chapter.id)
        voice_before = next(t for t in before['tracks'] if t['track_type'] == 'voice')['clips']
        service = LineService(LineRepository(self.session), RoleRepository(self.session), TTSProviderRepository(self.session), LLMProviderRepository(self.session))
        result = self.service.bind_asset(asset['id'], effect.id, service)
        after = timeline.get_chapter_timeline(project.id, chapter.id)
        self.assertTrue(result['timeline_updated'])
        self.assertEqual(after['status'], 'ready')
        self.assertEqual(next(t for t in after['tracks'] if t['track_type'] == 'voice')['clips'], voice_before)
        replaced = next(t for t in after['tracks'] if t['track_type'] == 'sfx')['clips'][0]
        self.assertNotEqual(replaced['asset_id'], target['asset_id'])
        self.assertEqual((replaced['start_ms'], replaced['volume_db'], replaced['fade_in_ms'], replaced['fade_out_ms']), (230, -18, 20, 40))

    def test_user_import_is_copied_deduplicated_and_deletable(self):
        source = self._wav()
        with patch("app.services.sound_library_service.getConfigPath", return_value=self.config_dir.name):
            imported = self.service.import_path(source, "自定义提示音", "foley", ["提示", "短音"])
            duplicate = self.service.import_path(source, "另一个名字", "foley", [])

        self.assertEqual(imported["id"], duplicate["id"])
        self.assertEqual(self.session.query(SoundLibraryAssetPO).count(), 1)
        self.assertNotEqual(os.path.abspath(source), imported["path"])
        self.assertTrue(os.path.isfile(imported["path"]))
        self.assertEqual(imported["duration_ms"], 500)
        self.assertEqual(imported["tags"], ["提示", "短音"])

        self.service.delete_user_asset(imported["id"])
        self.assertEqual(self.session.query(SoundLibraryAssetPO).count(), 0)
        self.assertFalse(os.path.exists(imported["path"]))

    def test_invalid_category_and_builtin_delete_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.import_path(self._wav(), category="unknown")
        builtin = self.service.list_assets(source_type="builtin")[0]
        self.assertTrue(self.service.resolve_path(builtin["id"]).is_file())
        with self.assertRaises(ValueError):
            self.service.delete_user_asset(builtin["id"])

    def _chapter(self, with_audio=True):
        project = ProjectPO(name="悬疑音效测试")
        self.session.add(project)
        self.session.flush()
        chapter = ChapterPO(project_id=project.id, title="雨夜来客")
        self.session.add(chapter)
        self.session.flush()
        lines = [LinePO(
            chapter_id=chapter.id, line_order=index + 1, track="voice",
            scene_title="楼道" if index < 2 else "屋内", text_content=f"台词{index + 1}",
            audio_path=self._wav(f"voice{index}.wav") if with_audio else None,
        ) for index in range(3)]
        self.session.add_all(lines)
        self.session.commit()
        with patch("app.services.sound_library_service.getConfigPath", return_value=self.config_dir.name):
            asset = self.service.import_path(self._wav("effect.wav"), "门外脚步", "footsteps")
        return project, chapter, lines, asset

    def _insert(self, asset, chapter, anchor=None, **kwargs):
        with patch("app.services.sound_library_service.getConfigPath", return_value=self.config_dir.name):
            return self.service.insert_asset(asset["id"], SoundLibraryInsertDTO(
                chapter_id=chapter.id, anchor_line_id=anchor.id if anchor else None, **kwargs,
            ))

    def test_insert_overlays_real_anchor_and_preserves_manual_edits(self):
        project, chapter, lines, asset = self._chapter()
        timeline = TimelineService(self.session)
        built = timeline.build_chapter_timeline(project.id, chapter.id)
        voice_clips = next(track["clips"] for track in built["tracks"] if track["track_type"] == "voice")
        timeline.update_clip(project.id, chapter.id, voice_clips[1]["id"], TimelineClipUpdateDTO(start_ms=2200, volume_db=-5))

        inserted = self._insert(asset, chapter, lines[1], volume_db=-18, duration_ms=400, fade_in_ms=100, fade_out_ms=200)
        self.assertFalse(inserted["placement_pending"])
        self.assertEqual(inserted["start_ms"], 2200)
        self.assertEqual(timeline.get_chapter_timeline(project.id, chapter.id)["status"], "ready")
        voice = self.session.get(TimelineClipPO, voice_clips[1]["id"])
        self.assertEqual((voice.start_ms, voice.volume_db, voice.is_user_edited), (2200, -5, True))
        effect = self.session.get(TimelineClipPO, inserted["clip_id"])
        self.assertEqual((effect.duration_ms, effect.volume_db, effect.fade_in_ms, effect.fade_out_ms), (400, -18, 100, 200))
        self.assertFalse(effect.is_user_edited)  # Cue parameters survive auto-builds independently.
        line = self.session.get(LinePO, inserted["line_id"])
        self.assertEqual((line.track, line.should_speak, line.status), ("sfx", 0, "done"))
        self.assertNotEqual(line.audio_path, asset["path"])
        self.assertEqual(Path(line.audio_path).read_bytes(), Path(asset["path"]).read_bytes())
        ordered = self.session.query(LinePO).filter(LinePO.chapter_id == chapter.id).order_by(LinePO.line_order).all()
        self.assertEqual([item.id for item in ordered], [lines[0].id, line.id, lines[1].id, lines[2].id])
        self.assertEqual([item.line_order for item in ordered], [1, 2, 3, 4])

    def test_insert_before_tts_retains_timing_and_mix_after_rebuild(self):
        project, chapter, lines, asset = self._chapter(with_audio=False)
        inserted = self._insert(asset, chapter, lines[1], placement="after", offset_ms=100, volume_db=-15)
        self.assertTrue(inserted["placement_pending"])
        timeline = TimelineService(self.session)
        missing = timeline.build_chapter_timeline(project.id, chapter.id)
        self.assertEqual(missing["status"], "missing_audio")
        self.assertEqual(missing["clip_count"], 0)
        for index, line in enumerate(lines):
            line.audio_path = self._wav(f"generated{index}.wav")
        self.session.commit()
        built = timeline.build_chapter_timeline(project.id, chapter.id)
        effect = next(clip for track in built["tracks"] for clip in track["clips"] if clip["line_id"] == inserted["line_id"])
        self.assertEqual((effect["start_ms"], effect["volume_db"]), (1100, -15))
        self.assertEqual(built["status"], "ready")
        voice_starts = [clip["start_ms"] for track in built["tracks"] if track["track_type"] == "voice" for clip in track["clips"]]
        self.assertEqual(voice_starts, [0, 500, 1000])
        rebuilt = timeline.build_chapter_timeline(project.id, chapter.id, force=True)
        effect_after = next(clip for track in rebuilt["tracks"] for clip in track["clips"] if clip["line_id"] == inserted["line_id"])
        self.assertEqual((effect_after["start_ms"], effect_after["volume_db"]), (1100, -15))

    def test_scene_start_uses_current_scene_and_duplicate_add_is_explicit(self):
        project, chapter, lines, asset = self._chapter()
        timeline = TimelineService(self.session)
        timeline.build_chapter_timeline(project.id, chapter.id)
        first = self._insert(asset, chapter, lines[1], placement="scene_start")
        second = self._insert(asset, chapter, lines[1], placement="scene_start")
        self.assertEqual(first["start_ms"], 0)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertNotEqual(first["line_id"], second["line_id"])
        third = self._insert(asset, chapter, lines[2], placement="scene_start")
        self.assertEqual(third["start_ms"], 1000)

    def test_failed_copy_rolls_back_new_line_and_all_order_changes(self):
        _, chapter, lines, asset = self._chapter()
        original = [(line.id, line.line_order) for line in lines]
        with patch("app.services.sound_library_service.shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self._insert(asset, chapter, lines[1])
        current = self.session.query(LinePO).order_by(LinePO.line_order).all()
        self.assertEqual([(line.id, line.line_order) for line in current], original)
        self.assertEqual(list(Path(self.config_dir.name).glob("assets/**/*.wav")), [])

    def test_cross_chapter_anchor_invalid_duration_and_cue_anchor_are_rejected(self):
        _, chapter, lines, asset = self._chapter()
        other = ChapterPO(project_id=chapter.project_id, title="另一章")
        self.session.add(other)
        self.session.commit()
        with self.assertRaisesRegex(ValueError, "不属于当前章节"):
            self._insert(asset, other, lines[0])
        with self.assertRaisesRegex(ValueError, "不能超过源音频"):
            self._insert(asset, chapter, lines[0], duration_ms=501)
        with self.assertRaisesRegex(ValueError, "淡入和淡出"):
            self._insert(asset, chapter, lines[0], fade_in_ms=300, fade_out_ms=300)
        first = self._insert(asset, chapter, lines[0])
        with self.assertRaisesRegex(ValueError, "原始音效行"):
            self._insert(asset, chapter, self.session.get(LinePO, first["line_id"]))

    def test_insert_does_not_hide_preexisting_stale_audio(self):
        project, chapter, lines, asset = self._chapter()
        timeline = TimelineService(self.session)
        timeline.build_chapter_timeline(project.id, chapter.id)
        lines[0].audio_path = self._wav("replacement.wav")
        self.session.commit()
        self.assertEqual(timeline.get_chapter_timeline(project.id, chapter.id)["status"], "stale")
        self._insert(asset, chapter, lines[1])
        self.assertEqual(timeline.get_chapter_timeline(project.id, chapter.id)["status"], "stale")

    def test_empty_chapter_accepts_multiple_independent_scene_sounds(self):
        project, _, _, asset = self._chapter()
        chapter = ChapterPO(project_id=project.id, title="尚无对白的场景")
        self.session.add(chapter)
        self.session.commit()
        first = self._insert(asset, chapter)
        second = self._insert(asset, chapter)
        built = TimelineService(self.session).build_chapter_timeline(project.id, chapter.id)
        self.assertNotEqual(first["line_id"], second["line_id"])
        self.assertEqual(built["status"], "ready")
        self.assertEqual(built["clip_count"], 2)
        self.assertEqual(built["duration_ms"], 500)


if __name__ == "__main__":
    unittest.main()
