"""Render the persisted chapter timeline into the final mixed WAV file."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import getConfigPath, getFfmpegPath
from app.models.po import AudioAssetPO, ChapterPO, ProjectPO, TimelineClipPO, TimelineTrackPO
from app.services.timeline_service import TimelineService


OUTPUT_SAMPLE_RATE = 44100
OUTPUT_CHANNELS = 2
MAX_RENDER_DURATION_MS = 4 * 60 * 60 * 1000
MAX_RENDER_CLIPS = 500


class TimelineRenderService:
    def __init__(self, db: Session):
        self.db = db

    def render_chapter(self, project_id: int, chapter_id: int) -> dict[str, Any]:
        project, chapter, clips, assets, tracks = self._load_render_state(project_id, chapter_id)
        timeline = TimelineService(self.db).get_chapter_timeline(project_id, chapter_id)
        self._validate_timeline(timeline, clips, assets)

        duration_ms = max(clip.start_ms + clip.duration_ms for clip in clips)
        output_dir = self._output_dir(project, chapter)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "timeline_mix.wav"
        manifest_path = output_dir / "timeline_render_manifest.json"
        temp_output = output_dir / f".timeline_mix_{uuid4().hex}.wav"
        active_clips = [clip for clip in clips if not clip.is_muted]

        try:
            if active_clips:
                self._render_active_clips(active_clips, assets, duration_ms, temp_output)
            else:
                self._render_silence(duration_ms, temp_output)
            os.replace(temp_output, output_path)
        except Exception:
            temp_output.unlink(missing_ok=True)
            raise

        render_fingerprint = self._render_fingerprint(clips, assets)
        rendered_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": 1,
            "render_engine": "ffmpeg_timeline_mix_v1",
            "project_id": project_id,
            "chapter_id": chapter_id,
            "chapter_title": chapter.title,
            "timeline_status": timeline["status"],
            "render_fingerprint": render_fingerprint,
            "rendered_at": rendered_at,
            "duration_ms": duration_ms,
            "clip_count": len(clips),
            "rendered_clip_count": len(active_clips),
            "muted_clip_count": len(clips) - len(active_clips),
            "output": {
                "path": str(output_path),
                "sample_rate": OUTPUT_SAMPLE_RATE,
                "channels": OUTPUT_CHANNELS,
                "codec": "pcm_s16le",
            },
            "track_revisions": {
                track.track_type: track.revision
                for track in tracks
            },
            "clips": [self._manifest_clip(clip, assets[clip.asset_id]) for clip in clips],
        }
        self._write_json_atomic(manifest_path, manifest)
        return self._result_payload(manifest, output_path, manifest_path)

    def get_latest_render(self, project_id: int, chapter_id: int) -> dict[str, Any]:
        project, chapter, clips, assets, _tracks = self._load_render_state(project_id, chapter_id)
        timeline = TimelineService(self.db).get_chapter_timeline(project_id, chapter_id)
        self._validate_timeline(timeline, clips, assets)
        output_dir = self._output_dir(project, chapter)
        output_path = output_dir / "timeline_mix.wav"
        manifest_path = output_dir / "timeline_render_manifest.json"
        if not output_path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError("当前章节还没有时间线混音成片")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("时间线渲染清单已损坏，请重新渲染") from exc
        if manifest.get("render_fingerprint") != self._render_fingerprint(clips, assets):
            raise ValueError("时间线已修改，旧成片已过期，请重新渲染")
        return self._result_payload(manifest, output_path, manifest_path)

    def latest_audio_path(self, project_id: int, chapter_id: int) -> Path:
        payload = self.get_latest_render(project_id, chapter_id)
        return Path(payload["audio_path"])

    def _load_render_state(self, project_id: int, chapter_id: int):
        project = self.db.get(ProjectPO, project_id)
        chapter = self.db.get(ChapterPO, chapter_id)
        if project is None:
            raise ValueError("项目不存在")
        if chapter is None or chapter.project_id != project_id:
            raise ValueError("章节不存在或不属于当前项目")
        clips = (
            self.db.query(TimelineClipPO)
            .filter(TimelineClipPO.project_id == project_id, TimelineClipPO.chapter_id == chapter_id)
            .order_by(TimelineClipPO.start_ms.asc(), TimelineClipPO.id.asc())
            .all()
        )
        assets = {
            asset.id: asset
            for asset in self.db.query(AudioAssetPO)
            .filter(AudioAssetPO.project_id == project_id)
            .all()
        }
        tracks = (
            self.db.query(TimelineTrackPO)
            .filter(TimelineTrackPO.project_id == project_id, TimelineTrackPO.chapter_id == chapter_id)
            .order_by(TimelineTrackPO.order_index.asc())
            .all()
        )
        return project, chapter, clips, assets, tracks

    @staticmethod
    def _validate_timeline(timeline: dict[str, Any], clips, assets) -> None:
        if timeline["status"] != "ready":
            raise ValueError(f"时间线状态为 {timeline['status']}，请先修复并刷新时间线")
        if not clips:
            raise ValueError("时间线没有可渲染片段")
        if len(clips) > MAX_RENDER_CLIPS:
            raise ValueError(f"单章时间线最多支持 {MAX_RENDER_CLIPS} 个片段")
        duration_ms = max(clip.start_ms + clip.duration_ms for clip in clips)
        if duration_ms <= 0 or duration_ms > MAX_RENDER_DURATION_MS:
            raise ValueError("时间线总时长无效或超过 4 小时")
        for clip in clips:
            asset = assets.get(clip.asset_id)
            if asset is None:
                raise ValueError(f"片段 #{clip.id} 缺少音频资产")
            if not os.path.isfile(asset.path):
                raise FileNotFoundError(f"片段 #{clip.id} 的音频文件不存在: {asset.path}")
            if clip.duration_ms <= 0 or clip.duration_ms > asset.duration_ms:
                raise ValueError(f"片段 #{clip.id} 的时长超出源音频范围")
            if clip.fade_in_ms < 0 or clip.fade_out_ms < 0 or clip.fade_in_ms + clip.fade_out_ms > clip.duration_ms:
                raise ValueError(f"片段 #{clip.id} 的淡入淡出设置无效")
            if not math.isfinite(float(clip.volume_db)) or not -60 <= float(clip.volume_db) <= 12:
                raise ValueError(f"片段 #{clip.id} 的音量设置无效")

    def _render_active_clips(self, clips, assets, duration_ms: int, output_path: Path) -> None:
        command = [getFfmpegPath(), "-nostdin", "-y"]
        filters = []
        outputs = []
        for index, clip in enumerate(clips):
            asset = assets[clip.asset_id]
            command.extend(["-i", asset.path])
            duration = clip.duration_ms / 1000
            chain = [
                f"[{index}:a]atrim=start=0:end={duration:.6f}",
                "asetpts=PTS-STARTPTS",
                f"aresample={OUTPUT_SAMPLE_RATE}",
            ]
            if asset.channels == 1:
                chain.append("pan=stereo|c0=c0|c1=c0")
            else:
                chain.append("aformat=sample_fmts=fltp:channel_layouts=stereo")
            chain.append(f"volume={float(clip.volume_db):.3f}dB")
            if clip.fade_in_ms:
                chain.append(f"afade=t=in:st=0:d={clip.fade_in_ms / 1000:.6f}")
            if clip.fade_out_ms:
                fade_start = max(0, clip.duration_ms - clip.fade_out_ms) / 1000
                chain.append(f"afade=t=out:st={fade_start:.6f}:d={clip.fade_out_ms / 1000:.6f}")
            chain.append(f"adelay={clip.start_ms}:all=1[c{index}]")
            filters.append(",".join(chain))
            outputs.append(f"[c{index}]")

        total_seconds = duration_ms / 1000
        filters.append(
            f"{''.join(outputs)}amix=inputs={len(outputs)}:duration=longest:dropout_transition=0:normalize=0,"
            f"apad=whole_dur={total_seconds:.6f},atrim=start=0:end={total_seconds:.6f},"
            "alimiter=limit=0.95:level=false:latency=true[out]"
        )
        command.extend([
            "-filter_complex", ";".join(filters),
            "-map", "[out]",
            "-ar", str(OUTPUT_SAMPLE_RATE),
            "-ac", str(OUTPUT_CHANNELS),
            "-c:a", "pcm_s16le",
            str(output_path),
        ])
        self._run_ffmpeg(command)

    def _render_silence(self, duration_ms: int, output_path: Path) -> None:
        self._run_ffmpeg([
            getFfmpegPath(), "-nostdin", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={OUTPUT_SAMPLE_RATE}:cl=stereo",
            "-t", f"{duration_ms / 1000:.6f}",
            "-c:a", "pcm_s16le",
            str(output_path),
        ])

    @staticmethod
    def _run_ffmpeg(command: list[str]) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc))[-2000:]
            raise RuntimeError(f"FFmpeg 时间线混音失败: {detail}") from exc

    @staticmethod
    def _output_dir(project: ProjectPO, chapter: ChapterPO) -> Path:
        root = Path(project.project_root_path or getConfigPath()).expanduser().resolve()
        return root / str(project.id) / str(chapter.id) / "audio" / "result"

    @classmethod
    def _render_fingerprint(cls, clips, assets) -> str:
        payload = []
        for clip in clips:
            asset = assets.get(clip.asset_id)
            stat = None
            if asset:
                try:
                    file_stat = os.stat(asset.path)
                    stat = [file_stat.st_size, file_stat.st_mtime_ns]
                except OSError:
                    stat = [None, None]
            payload.append({
                "id": clip.id,
                "asset_id": clip.asset_id,
                "asset_path": asset.path if asset else None,
                "asset_checksum": asset.checksum if asset else None,
                "asset_stat": stat,
                "start_ms": clip.start_ms,
                "duration_ms": clip.duration_ms,
                "volume_db": clip.volume_db,
                "fade_in_ms": clip.fade_in_ms,
                "fade_out_ms": clip.fade_out_ms,
                "is_muted": bool(clip.is_muted),
                "revision": clip.revision,
            })
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _manifest_clip(clip: TimelineClipPO, asset: AudioAssetPO) -> dict[str, Any]:
        return {
            "id": clip.id,
            "track_id": clip.track_id,
            "track_type": clip.track_type,
            "line_id": clip.line_id,
            "asset_id": clip.asset_id,
            "asset_path": asset.path,
            "asset_checksum": asset.checksum,
            "start_ms": clip.start_ms,
            "duration_ms": clip.duration_ms,
            "volume_db": clip.volume_db,
            "fade_in_ms": clip.fade_in_ms,
            "fade_out_ms": clip.fade_out_ms,
            "is_muted": bool(clip.is_muted),
            "revision": clip.revision,
        }

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".json") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            temp_path = Path(stream.name)
        os.replace(temp_path, path)

    @staticmethod
    def _result_payload(manifest: dict[str, Any], output_path: Path, manifest_path: Path) -> dict[str, Any]:
        safe_title = re.sub(r"[\\/:*?\"<>|]+", "_", str(manifest.get("chapter_title") or "chapter")).strip(" ._")
        return {
            "audio_path": str(output_path),
            "manifest_path": str(manifest_path),
            "file_name": f"{safe_title or 'chapter'}_timeline_mix.wav",
            "rendered_at": manifest["rendered_at"],
            "duration_ms": manifest["duration_ms"],
            "clip_count": manifest["clip_count"],
            "rendered_clip_count": manifest["rendered_clip_count"],
            "muted_clip_count": manifest["muted_clip_count"],
            "render_fingerprint": manifest["render_fingerprint"],
        }
