"""Build and read the first real, audio-duration-backed chapter timeline."""

from __future__ import annotations

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
            status = self._effective_status(track, source_fingerprint, bool(track_clips), bool(lines))
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
            self._effective_status(track, source_fingerprint, bool(existing_clips), bool(lines))
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
            self.db.execute(delete(TimelineClipPO).where(TimelineClipPO.chapter_id == chapter.id))
            cursors = 0
            track_by_type = {track.track_type: track for track in tracks}
            missing_tracks: set[str] = set()
            for line in lines:
                track_type = self._track_type(line)
                asset = self._register_line_assets(project_id, chapter.id, line, track_type)
                if asset is None or asset.duration_ms <= 0:
                    missing_tracks.add(track_type)
                    continue
                track = track_by_type[track_type]
                self.db.add(TimelineClipPO(
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
                ))
                cursors += asset.duration_ms
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
    def clear_line_timeline(db: Session, line_id: int) -> None:
        """Remove clips/assets owned by one line and mark its track stale."""
        track_ids = list(db.execute(select(TimelineClipPO.track_id).where(TimelineClipPO.line_id == line_id)).scalars())
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.line_id == line_id))
        db.execute(delete(AudioAssetPO).where(AudioAssetPO.line_id == line_id))
        if track_ids:
            db.execute(
                update(TimelineTrackPO)
                .where(TimelineTrackPO.id.in_(track_ids))
                .values(status="stale", last_error="台词或音频资产已变化")
            )

    @staticmethod
    def clear_chapter_timeline(db: Session, chapter_id: int) -> None:
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.chapter_id == chapter_id))
        db.execute(delete(AudioAssetPO).where(AudioAssetPO.chapter_id == chapter_id))
        db.execute(delete(TimelineTrackPO).where(TimelineTrackPO.chapter_id == chapter_id))

    @staticmethod
    def clear_project_timeline(db: Session, project_id: int) -> None:
        db.execute(delete(TimelineClipPO).where(TimelineClipPO.project_id == project_id))
        db.execute(delete(AudioAssetPO).where(AudioAssetPO.project_id == project_id))
        db.execute(delete(TimelineTrackPO).where(TimelineTrackPO.project_id == project_id))

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
    def _effective_status(track: TimelineTrackPO, fingerprint: str, has_clips: bool, has_lines: bool) -> str:
        if track.status == "failed" and track.source_fingerprint == fingerprint:
            return "failed"
        if track.source_fingerprint and track.source_fingerprint != fingerprint:
            return "stale"
        if not track.source_fingerprint:
            return "not_built"
        if not has_clips and has_lines:
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
                metadata_json={"source": source_kind},
            )
            self.db.add(asset)
            self.db.flush()
            return asset

        asset.chapter_id = chapter_id
        asset.line_id = line_id
        asset.asset_type = asset_type
        asset.duration_ms = duration_ms
        asset.sample_rate = sample_rate
        asset.channels = channels
        asset.mime_type = mimetypes.guess_type(path)[0]
        asset.checksum = checksum
        asset.metadata_json = {**(asset.metadata_json or {}), "source": source_kind}
        self.db.flush()
        return asset

    @staticmethod
    def _selected_audio_path(line: LinePO) -> str | None:
        active_variant = next(
            (item for item in TimelineService._items(line.audio_variants) if item.get("id") == line.active_audio_variant_id),
            None,
        )
        if active_variant and active_variant.get("audio_path"):
            return active_variant["audio_path"]
        active_version = next(
            (item for item in TimelineService._items(line.audio_versions) if item.get("id") == line.active_audio_version_id),
            None,
        )
        if active_version and active_version.get("audio_path"):
            return active_version["audio_path"]
        return line.audio_path

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
