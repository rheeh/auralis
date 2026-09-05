"""Build and read the first real, audio-duration-backed chapter timeline."""

from __future__ import annotations

from app.services.audio_selection import selected_audio_path

import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
from collections import defaultdict
from typing import Any

import soundfile as sf
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.dto.timeline_dto import TimelineClipUpdateDTO
from app.models.po import (
    AudioAssetPO,
    ChapterPO,
    LinePO,
    TimelineClipPO,
    TimelineTrackPO,
)


TRACK_TYPES = ("voice", "narration", "sfx", "bgm")
TRACK_NAMES = {
    "voice": "人物声",
    "narration": "旁白",
    "sfx": "音效",
    "bgm": "BGM",
}


class TimelineService:
    def __init__(self, db: Session):
        self.db = db

    def get_chapter_timeline(self, project_id: int, chapter_id: int) -> dict[str, Any]:
        chapter = self._get_chapter(project_id, chapter_id)
        tracks = (
            self.db.query(TimelineTrackPO)
            .filter(TimelineTrackPO.chapter_id == chapter.id)
            .order_by(TimelineTrackPO.order_index.asc())
            .all()
        )
        clips = (
            self.db.query(TimelineClipPO)
            .filter(TimelineClipPO.chapter_id == chapter.id)
            .order_by(TimelineClipPO.start_ms.asc(), TimelineClipPO.id.asc())
            .all()
        )
        lines = {
            line.id: line
            for line in self.db.query(LinePO)
            .filter(LinePO.chapter_id == chapter.id)
            .all()
        }
        assets = {
            asset.id: asset
            for asset in self.db.query(AudioAssetPO)
            .filter(AudioAssetPO.project_id == project_id)
            .all()
        }
        clips_by_track: dict[int, list[TimelineClipPO]] = defaultdict(list)
        for clip in clips:
            clips_by_track[clip.track_id].append(clip)
        source_fingerprint = self._source_fingerprint(lines.values())
        track_payloads = []
        statuses = []
        for track in tracks:
            track_clips = clips_by_track.get(track.id, [])
            track_lines = [line for line in lines.values() if self._track_type(line) == track.track_type]
            clip_line_ids = {clip.line_id for clip in track_clips if clip.line_id is not None}
            missing_track_audio = any(line.id not in clip_line_ids for line in track_lines)
            status = self._effective_status(
                track,
                source_fingerprint,
                bool(track_lines),
                missing_track_audio,
            )
            statuses.append(status)
            track_payloads.append({
                "id": track.id,
                "track_type": track.track_type,
                "name": track.name,
                "order_index": track.order_index,
                "revision": track.revision,
                "status": status,
                "build_mode": track.build_mode,
                "last_error": track.last_error,
                "clips": [
                    self._clip_payload(clip, assets.get(clip.asset_id), lines.get(clip.line_id))
                    for clip in track_clips
                ],
            })

        return {
            "project_id": project_id,
            "chapter_id": chapter_id,
            "chapter_title": chapter.title,
            "status": self._aggregate_status(statuses),
            "track_count": len(tracks),
            "clip_count": len(clips),
            "duration_ms": max((clip.start_ms + clip.duration_ms for clip in clips), default=0),
            "tracks": track_payloads,
        }

    def build_chapter_timeline(
        self,
        project_id: int,
        chapter_id: int,
        *,
        force: bool = False,
        overwrite_manual: bool = False,
    ) -> dict[str, Any]:
        chapter = self._get_chapter(project_id, chapter_id)
        tracks = self._ensure_tracks(project_id, chapter.id)
        lines = (
            self.db.query(LinePO)
            .filter(LinePO.chapter_id == chapter.id)
            .order_by(LinePO.line_order.asc(), LinePO.id.asc())
            .all()
        )
        source_fingerprint = self._source_fingerprint(lines)
        existing_clips = (
            self.db.query(TimelineClipPO)
            .filter(TimelineClipPO.chapter_id == chapter.id)
            .all()
        )
        current_status = self._aggregate_status([
            self._effective_status(
                track,
                source_fingerprint,
                any(self._track_type(line) == track.track_type for line in lines),
                any(
                    self._track_type(line) == track.track_type
                    and line.id not in {clip.line_id for clip in existing_clips}
                    for line in lines
                ),
            )
            for track in tracks
        ])
        has_manual_clips = any(clip.is_user_edited for clip in existing_clips)
        if existing_clips and current_status == "ready" and not force:
            return self.get_chapter_timeline(project_id, chapter_id)
        if has_manual_clips and not overwrite_manual:
            for track in tracks:
                track.status = "stale"
                track.last_error = "存在用户编辑片段，自动构建已保护现有调整"
            self.db.commit()
            return self.get_chapter_timeline(project_id, chapter_id)

        # Commit the building marker first so a later failure is visible.
        for track in tracks:
            track.status = "building"
            track.build_mode = "auto"
            track.last_error = None
            if existing_clips:
                track.revision += 1
        self.db.commit()
        try:
            self.db.query(TimelineClipPO).filter(TimelineClipPO.chapter_id == chapter.id).delete(
                synchronize_session="fetch"
            )
            cursors = 0
            track_by_type = {track.track_type: track for track in tracks}
            missing_tracks: set[str] = set()
            built_clips: list[TimelineClipPO] = []
            for line in lines:
                if self.sound_library_cue(line):
                    continue
                track_type = self._track_type(line)
                asset = self._register_line_assets(project_id, chapter.id, line, track_type)
                if asset is None or asset.duration_ms <= 0:
                    missing_tracks.add(track_type)
                    continue
                track = track_by_type[track_type]
                clip = TimelineClipPO(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    track_id=track.id,
                    line_id=line.id,
                    asset_id=asset.id,
                    track_type=track_type,
                    start_ms=cursors,
                    duration_ms=asset.duration_ms,
                    volume_db=0.0,
                    fade_in_ms=0,
                    fade_out_ms=0,
                    is_muted=False,
                    is_user_edited=False,
                    revision=track.revision,
                )
                self.db.add(clip)
                built_clips.append(clip)
                cursors += asset.duration_ms
            # Quick-added ambience and foley overlay their anchor instead of
            # pushing the whole chapter forward by their source-file duration.
            for line in lines:
                if not self.sound_library_cue(line):
                    continue
                track_type = self._track_type(line)
                clip = self.add_sound_library_clip(
                    project_id, chapter.id, line, track_by_type[track_type], built_clips
                )
                if clip is None:
                    missing_tracks.add(track_type)
                else:
                    built_clips.append(clip)
            for track in tracks:
                track.source_fingerprint = source_fingerprint
                track.status = "missing_audio" if track.track_type in missing_tracks else "ready"
                track.last_error = None
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            for track in self.db.query(TimelineTrackPO).filter(TimelineTrackPO.chapter_id == chapter.id).all():
                track.status = "failed"
                track.last_error = str(exc)[:1000]
            self.db.commit()
            raise
        return self.get_chapter_timeline(project_id, chapter_id)

    @staticmethod
    def sound_library_cue(line: LinePO) -> dict[str, Any] | None:
        return next((event for event in TimelineService._items(line.audio_events)
                     if event.get("type") == "sound_library_placement"), None)

    def add_sound_library_clip(
        self, project_id: int, chapter_id: int, line: LinePO,
        track: TimelineTrackPO, clips: list[TimelineClipPO],
    ) -> TimelineClipPO | None:
        """Place a persistent library cue using its anchor's real audio timing."""
        cue = self.sound_library_cue(line)
        if not cue:
            return None
        anchor_id = cue.get("anchor_line_id")
        anchor_clip = next((clip for clip in clips if clip.line_id == anchor_id), None)
        if anchor_id and anchor_clip is None:
            return None
        asset = self._register_line_assets(project_id, chapter_id, line, self._track_type(line))
        if asset is None or asset.duration_ms <= 0:
            return None
        duration_ms = min(asset.duration_ms, max(1, int(cue.get("duration_ms") or asset.duration_ms)))
        start_ms = anchor_clip.start_ms if anchor_clip else 0
        if anchor_clip and cue.get("placement") == "after":
            start_ms += anchor_clip.duration_ms
        elif anchor_clip and cue.get("placement") == "before":
            start_ms -= duration_ms
        start_ms = max(0, start_ms + int(cue.get("offset_ms") or 0))
        fade_in = min(duration_ms, max(0, int(cue.get("fade_in_ms") or 0)))
        fade_out = min(duration_ms - fade_in, max(0, int(cue.get("fade_out_ms") or 0)))
        clip = TimelineClipPO(
            project_id=project_id, chapter_id=chapter_id, track_id=track.id,
            line_id=line.id, asset_id=asset.id, track_type=self._track_type(line),
            start_ms=start_ms, duration_ms=duration_ms,
            volume_db=max(-60, min(12, float(cue.get("volume_db", -12)))),
            fade_in_ms=fade_in, fade_out_ms=fade_out,
            is_muted=False, is_user_edited=False, revision=track.revision,
        )
        self.db.add(clip)
        self.db.flush()
        return clip

    def update_clip(
        self,
        project_id: int,
        chapter_id: int,
        clip_id: int,
        dto: TimelineClipUpdateDTO,
    ) -> dict[str, Any]:
        self._get_chapter(project_id, chapter_id)
        clip = (
            self.db.query(TimelineClipPO)
            .filter(
                TimelineClipPO.id == clip_id,
                TimelineClipPO.project_id == project_id,
                TimelineClipPO.chapter_id == chapter_id,
            )
            .one_or_none()
        )
        if clip is None:
            raise ValueError("时间线片段不存在")
        asset = self.db.get(AudioAssetPO, clip.asset_id)
        if asset is None:
            raise ValueError("片段关联的音频资产不存在")

        values = dto.model_dump(exclude_unset=True)
        duration_ms = int(values.get("duration_ms", clip.duration_ms))
        fade_in_ms = int(values.get("fade_in_ms", clip.fade_in_ms))
        fade_out_ms = int(values.get("fade_out_ms", clip.fade_out_ms))
        if duration_ms > asset.duration_ms:
            raise ValueError(f"片段长度不能超过源音频时长 {asset.duration_ms} ms")
        if fade_in_ms + fade_out_ms > duration_ms:
            raise ValueError("淡入和淡出总时长不能超过片段长度")

        for field, value in values.items():
            setattr(clip, field, value)
        clip.is_user_edited = True
        clip.revision += 1
        track = self.db.get(TimelineTrackPO, clip.track_id)
        if track:
            track.build_mode = "manual"
            track.status = "ready"
            track.last_error = None
            track.revision += 1
        self.db.commit()
        return self.get_chapter_timeline(project_id, chapter_id)

    @staticmethod
    def clear_line_timeline(db: Session, line_id: int) -> None:
        """Remove one line's clips and only collect assets no longer referenced."""
        asset_ids = list(db.execute(select(TimelineClipPO.asset_id).where(TimelineClipPO.line_id == line_id)).scalars())
        asset_ids.extend(db.execute(select(AudioAssetPO.id).where(AudioAssetPO.line_id == line_id)).scalars())
        track_ids = list(db.execute(select(TimelineClipPO.track_id).where(TimelineClipPO.line_id == line_id)).scalars())
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.line_id == line_id))
        TimelineService._delete_unreferenced_assets(db, asset_ids)
        if track_ids:
            db.execute(
                update(TimelineTrackPO)
                .where(TimelineTrackPO.id.in_(track_ids))
                .values(status="stale", last_error="台词或音频资产已变化")
            )

    @staticmethod
    def clear_chapter_timeline(db: Session, chapter_id: int) -> None:
        asset_ids = list(db.execute(select(TimelineClipPO.asset_id).where(TimelineClipPO.chapter_id == chapter_id)).scalars())
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.chapter_id == chapter_id))
        asset_ids.extend(
            db.execute(select(AudioAssetPO.id).where(AudioAssetPO.chapter_id == chapter_id)).scalars()
        )
        TimelineService._delete_unreferenced_assets(db, asset_ids)
        db.execute(delete(TimelineTrackPO).where(TimelineTrackPO.chapter_id == chapter_id))

    @staticmethod
    def clear_project_timeline(db: Session, project_id: int) -> None:
        asset_ids = list(db.execute(select(TimelineClipPO.asset_id).where(TimelineClipPO.project_id == project_id)).scalars())
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.project_id == project_id))
        asset_ids.extend(
            db.execute(select(AudioAssetPO.id).where(AudioAssetPO.project_id == project_id)).scalars()
        )
        TimelineService._delete_unreferenced_assets(db, asset_ids)
        db.execute(delete(TimelineTrackPO).where(TimelineTrackPO.project_id == project_id))

    @staticmethod
    def _delete_unreferenced_assets(db: Session, asset_ids) -> None:
        unique_ids = {asset_id for asset_id in asset_ids if asset_id is not None}
        if not unique_ids:
            return
        referenced = set(
            db.execute(
                select(TimelineClipPO.asset_id)
                .where(TimelineClipPO.asset_id.in_(unique_ids))
            ).scalars()
        )
        deletable = unique_ids - referenced
        if deletable:
            db.execute(delete(AudioAssetPO).where(AudioAssetPO.id.in_(deletable)))

    @staticmethod
    def invalidate_line(db: Session, line_id: int, reason: str = "台词或音频版本已变化") -> None:
        track_ids = list(db.execute(select(TimelineClipPO.track_id).where(TimelineClipPO.line_id == line_id)).scalars())
        if track_ids:
            db.execute(
                update(TimelineTrackPO)
                .where(TimelineTrackPO.id.in_(track_ids))
                .values(status="stale", last_error=reason)
            )
            db.commit()

    @staticmethod
    def _effective_status(
        track: TimelineTrackPO,
        fingerprint: str,
        has_track_lines: bool,
        missing_track_audio: bool,
    ) -> str:
        if track.status == "failed" and track.source_fingerprint == fingerprint:
            return "failed"
        if track.source_fingerprint and track.source_fingerprint != fingerprint:
            return "stale"
        if not track.source_fingerprint:
            return "not_built"
        if has_track_lines and missing_track_audio:
            return "missing_audio"
        return track.status or "not_built"

    @staticmethod
    def _aggregate_status(statuses: list[str]) -> str:
        for status in ("failed", "stale", "missing_audio", "not_built", "building"):
            if status in statuses:
                return status
        return "ready" if statuses else "not_built"

    @classmethod
    def _source_fingerprint(cls, lines) -> str:
        source = []
        for line in sorted(lines, key=lambda item: (item.line_order or 0, item.id or 0)):
            path = cls._normalise_path(cls._selected_audio_path(line))
            stat = None
            try:
                file_stat = os.stat(path)
                stat = [file_stat.st_size, file_stat.st_mtime_ns]
            except OSError:
                stat = [None, None]
            source.append({
                "id": line.id,
                "order": line.line_order,
                "track": cls._track_type(line),
                "path": path,
                "stat": stat,
                "active_version": line.active_audio_version_id,
                "active_variant": line.active_audio_variant_id,
            })
        return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _get_chapter(self, project_id: int, chapter_id: int) -> ChapterPO:
        chapter = (
            self.db.query(ChapterPO)
            .filter(ChapterPO.id == chapter_id, ChapterPO.project_id == project_id)
            .one_or_none()
        )
        if chapter is None:
            raise ValueError("章节不存在或不属于当前项目")
        return chapter

    def _ensure_tracks(self, project_id: int, chapter_id: int) -> list[TimelineTrackPO]:
        tracks = {
            track.track_type: track
            for track in self.db.query(TimelineTrackPO)
            .filter(TimelineTrackPO.chapter_id == chapter_id)
            .all()
        }
        for order_index, track_type in enumerate(TRACK_TYPES):
            if track_type not in tracks:
                track = TimelineTrackPO(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    track_type=track_type,
                    name=TRACK_NAMES[track_type],
                    order_index=order_index,
                    revision=1,
                )
                self.db.add(track)
                tracks[track_type] = track
        self.db.flush()
        return [tracks[track_type] for track_type in TRACK_TYPES]

    @staticmethod
    def _track_type(line: LinePO) -> str:
        track = (line.track or "").strip().lower()
        if track in TRACK_TYPES:
            return track
        if (line.line_type or "").strip().lower() == "narration":
            return "narration"
        if (line.line_type or "").strip().lower() in {"sfx", "bgm"}:
            return (line.line_type or "sfx").strip().lower()
        return "voice"

    def _register_line_assets(
        self,
        project_id: int,
        chapter_id: int,
        line: LinePO,
        track_type: str,
    ) -> AudioAssetPO | None:
        candidates: list[tuple[str, str, str | None]] = []
        base_type = track_type if track_type in {"sfx", "bgm"} else "tts_take"
        if line.audio_path:
            candidates.append((line.audio_path, base_type, "legacy_audio_path"))
        for item in self._items(line.audio_versions):
            if isinstance(item, dict) and item.get("audio_path"):
                candidates.append((item["audio_path"], "tts_take", "audio_version"))
        for item in self._items(line.audio_variants):
            if isinstance(item, dict) and item.get("audio_path"):
                candidates.append((item["audio_path"], "processed", "audio_variant"))

        assets_by_path: dict[str, AudioAssetPO] = {}
        for raw_path, asset_type, source_kind in candidates:
            path = self._normalise_path(raw_path)
            if not path or not os.path.isfile(path):
                continue
            asset = self._upsert_asset(project_id, chapter_id, line.id, path, asset_type, source_kind)
            assets_by_path[path] = asset

        selected_path = self._selected_audio_path(line)
        if not selected_path:
            return None
        return assets_by_path.get(self._normalise_path(selected_path))

    def _upsert_asset(
        self,
        project_id: int,
        chapter_id: int,
        line_id: int,
        path: str,
        asset_type: str,
        source_kind: str,
    ) -> AudioAssetPO:
        asset = (
            self.db.query(AudioAssetPO)
            .filter(AudioAssetPO.project_id == project_id, AudioAssetPO.path == path)
            .one_or_none()
        )
        duration_ms, sample_rate, channels = self._probe_audio(path)
        checksum = self._checksum(path)
        if asset is None:
            asset = AudioAssetPO(
                project_id=project_id,
                chapter_id=chapter_id,
                line_id=line_id,
                asset_type=asset_type,
                path=path,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                channels=channels,
                mime_type=mimetypes.guess_type(path)[0],
                checksum=checksum,
                revision=1,
                metadata_json={
                    "source": source_kind,
                    "source_refs": [{"chapter_id": chapter_id, "line_id": line_id, "source": source_kind}],
                },
            )
            self.db.add(asset)
            self.db.flush()
            return asset

        # The asset is project-scoped and may be referenced by many clips,
        # including BGM/SFX reused across chapters. Keep the first source
        # pointers for provenance instead of pretending the latest line owns it.
        metadata = dict(asset.metadata_json or {})
        source_refs = list(metadata.get("source_refs") or [])
        source_ref = {"chapter_id": chapter_id, "line_id": line_id, "source": source_kind}
        if source_ref not in source_refs:
            source_refs.append(source_ref)
        metadata["source_refs"] = source_refs
        asset.asset_type = asset_type
        asset.duration_ms = duration_ms
        asset.sample_rate = sample_rate
        asset.channels = channels
        asset.mime_type = mimetypes.guess_type(path)[0]
        asset.checksum = checksum
        metadata["source"] = source_kind
        asset.metadata_json = metadata
        self.db.flush()
        return asset

    @staticmethod
    def _selected_audio_path(line: LinePO) -> str | None:
        return selected_audio_path(line) or None

    @staticmethod
    def _normalise_path(path: str | None) -> str:
        return os.path.abspath(os.path.expanduser(path or "")) if path else ""

    @staticmethod
    def _items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError):
                return []
            return [item for item in decoded if isinstance(item, dict)] if isinstance(decoded, list) else []
        return []

    @staticmethod
    def _checksum(path: str) -> str | None:
        try:
            digest = hashlib.sha256()
            with open(path, "rb") as file_handle:
                for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return None

    @staticmethod
    def _probe_audio(path: str) -> tuple[int, int | None, int | None]:
        try:
            info = sf.info(path)
            return max(1, round(info.frames / info.samplerate * 1000)), info.samplerate, info.channels
        except Exception:
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                return 0, None, None
            try:
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return max(1, round(float(result.stdout.strip()) * 1000)), None, None
            except (OSError, ValueError, subprocess.CalledProcessError):
                return 0, None, None

    @staticmethod
    def _clip_payload(clip: TimelineClipPO, asset: AudioAssetPO | None, line: LinePO | None) -> dict[str, Any]:
        return {
            "id": clip.id,
            "line_id": clip.line_id,
            "asset_id": clip.asset_id,
            "track_type": clip.track_type,
            "start_ms": clip.start_ms,
            "duration_ms": clip.duration_ms,
            "volume_db": clip.volume_db,
            "fade_in_ms": clip.fade_in_ms,
            "fade_out_ms": clip.fade_out_ms,
            "is_muted": bool(clip.is_muted),
            "is_user_edited": bool(clip.is_user_edited),
            "revision": clip.revision,
            "line": {
                "id": line.id,
                "text_content": line.text_content,
                "scene_title": line.scene_title,
                "status": line.status,
                "is_done": line.is_done,
                "line_order": line.line_order,
            } if line else None,
            "asset": {
                "id": asset.id,
                "type": asset.asset_type,
                "path": asset.path,
                "duration_ms": asset.duration_ms,
                "mime_type": asset.mime_type,
                "revision": asset.revision,
                "status": "ready" if os.path.isfile(asset.path) else "missing",
            } if asset else None,
        }
