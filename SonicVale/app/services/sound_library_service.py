from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audio_metadata import probe_audio
from app.core.config import getConfigPath
from app.dto.sound_library_dto import SoundLibraryInsertDTO
from app.models.po import ChapterPO, LinePO, SoundLibraryAssetPO, TimelineClipPO, TimelineTrackPO
from app.services.timeline_service import TimelineService


SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
CATEGORIES = {"ambience", "weather", "doors", "footsteps", "impacts", "foley", "bgm"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024


class SoundLibraryService:
    def __init__(self, db: Session, builtin_root: str | Path | None = None):
        self.db = db
        self.builtin_root = Path(builtin_root) if builtin_root else self._find_builtin_root()
        self._builtin_by_id: dict[str, dict[str, Any]] | None = None

    def bind_asset(self, asset_id: str, line_id: int, line_service) -> dict:
        line = self.db.get(LinePO, line_id)
        if not line or (line.track or line.line_type) not in {"sfx", "bgm"}:
            raise ValueError("请选择音效或 BGM 台词")
        chapter = self.db.get(ChapterPO, line.chapter_id)
        if not chapter:
            raise ValueError("音效所属章节不存在")
        source = self.resolve_path(asset_id)
        if self._audio_info(source)[0] <= 0:
            raise ValueError("音效长度不可用")
        timeline = TimelineService(self.db)
        previously_ready = timeline.get_chapter_timeline(chapter.project_id, chapter.id)["status"] == "ready"
        target = line_service.attach_audio_asset(line_id, str(source))
        updated = timeline.refresh_material_audio(line, previously_ready=previously_ready)
        return {"line_id": line_id, "audio_path": target, "timeline_updated": updated}

    def list_assets(
        self,
        source_type: str = "all",
        category: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        if source_type in {"all", "builtin"}:
            assets.extend(self._builtins().values())
        if source_type in {"all", "user"}:
            rows = self.db.execute(
                select(SoundLibraryAssetPO).order_by(SoundLibraryAssetPO.created_at.desc())
            ).scalars().all()
            assets.extend(self._serialize_user(row) for row in rows)

        normalized_category = self._normalize_category(category, allow_empty=True)
        query = (keyword or "").strip().lower()
        if normalized_category:
            assets = [asset for asset in assets if asset["category"] == normalized_category]
        if query:
            assets = [
                asset for asset in assets
                if query in " ".join([
                    asset["name"], asset["category"], *asset.get("tags", [])
                ]).lower()
            ]
        return assets

    def import_path(
        self,
        source_path: str,
        name: str | None = None,
        category: str = "foley",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        self._validate_audio_file(source)
        normalized_name = self._normalize_name(name or source.stem)
        normalized_category = self._normalize_category(category)
        normalized_tags = self._normalize_tags(tags)
        checksum = self._checksum(source)
        existing = self.db.execute(
            select(SoundLibraryAssetPO).where(SoundLibraryAssetPO.checksum == checksum)
        ).scalar_one_or_none()
        if existing and Path(existing.path).is_file():
            return self._serialize_user(existing)
        if existing:
            self.db.delete(existing)
            self.db.commit()

        library_dir = Path(getConfigPath()) / "sound_library" / "user"
        library_dir.mkdir(parents=True, exist_ok=True)
        target = library_dir / f"{uuid4().hex}{source.suffix.lower()}"
        try:
            shutil.copy2(source, target)
            duration_ms, sample_rate, channels = self._audio_info(target)
            row = SoundLibraryAssetPO(
                name=normalized_name,
                category=normalized_category,
                tags=normalized_tags,
                path=str(target),
                original_name=source.name,
                source_type="user",
                license="user-provided",
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                channels=channels,
                mime_type=mimetypes.guess_type(target.name)[0] or "audio/octet-stream",
                checksum=checksum,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        except Exception:
            self.db.rollback()
            target.unlink(missing_ok=True)
            raise
        return self._serialize_user(row)

    def resolve_path(self, asset_id: str) -> Path:
        if asset_id.startswith("builtin_"):
            asset = self._builtins().get(asset_id)
            if not asset:
                raise ValueError("内置素材不存在")
            path = Path(asset["path"])
        elif asset_id.startswith("user_"):
            row = self._get_user(asset_id)
            path = Path(row.path)
        else:
            raise ValueError("素材 ID 无效")
        if not path.is_file():
            raise FileNotFoundError(f"素材文件不存在: {path}")
        return path

    def insert_asset(self, asset_id: str, dto: SoundLibraryInsertDTO) -> dict[str, Any]:
        """Copy a library sound and insert its cue atomically, preserving existing edits.

        Timing intent lives on the cue so sounds added before TTS can be placed
        against real audio durations when the timeline is built later.
        """
        chapter = self.db.get(ChapterPO, dto.chapter_id)
        if chapter is None:
            raise ValueError("章节不存在")
        lines = self.db.query(LinePO).filter(LinePO.chapter_id == chapter.id).order_by(
            LinePO.line_order.asc(), LinePO.id.asc()
        ).all()
        anchor = next((line for line in lines if line.id == dto.anchor_line_id), None)
        if dto.anchor_line_id is not None and anchor is None:
            raise ValueError("定位台词不存在或不属于当前章节")
        if any(not TimelineService.sound_library_cue(line) for line in lines) and anchor is None:
            raise ValueError("请选择当前章节中的定位台词")
        if anchor and TimelineService.sound_library_cue(anchor):
            raise ValueError("请选择对白、旁白或原始音效行作为定位台词")
        source = self.resolve_path(asset_id)
        asset = self._builtins()[asset_id] if asset_id.startswith("builtin_") else self._serialize_user(self._get_user(asset_id))
        source_duration = self._audio_info(source)[0]
        duration = dto.duration_ms or source_duration
        if not source_duration or duration > source_duration:
            raise ValueError(f"音效长度不能超过源音频时长 {source_duration} ms")
        if dto.fade_in_ms + dto.fade_out_ms > duration:
            raise ValueError("淡入和淡出总时长不能超过音效长度")

        if dto.placement == "scene_start" and anchor:
            # Repeated scene titles later in a chapter are separate occurrences.
            anchor_index = lines.index(anchor)
            while anchor_index > 0 and lines[anchor_index - 1].scene_title == anchor.scene_title:
                anchor_index -= 1
            anchor = next((line for line in lines[anchor_index:] if not TimelineService.sound_library_cue(line)), anchor)
        insertion_index = lines.index(anchor) + int(dto.placement == "after") if anchor else 0
        old_fingerprint = TimelineService._source_fingerprint(lines)
        tracks = self.db.query(TimelineTrackPO).filter(TimelineTrackPO.chapter_id == chapter.id).all()
        duplicate = any(
            (cue := TimelineService.sound_library_cue(line))
            and cue.get("library_asset_id") == asset_id
            and cue.get("anchor_line_id") == (anchor.id if anchor else None)
            for line in lines
        )
        cue = {
            **dto.model_dump(exclude={"chapter_id"}),
            "type": "sound_library_placement",
            "anchor_line_id": anchor.id if anchor else None,
            "library_asset_id": asset_id,
            "duration_ms": duration,
            "license": asset.get("license"),
            "source_url": asset.get("source_url"),
        }
        target = None
        clip = None
        try:
            new_line = LinePO(
                chapter_id=chapter.id,
                line_order=insertion_index + 1,
                text_content=asset["name"],
                line_type="bgm" if asset["category"] == "bgm" else "sfx",
                track="bgm" if asset["category"] == "bgm" else "sfx",
                should_speak=0,
                scene_title=anchor.scene_title if anchor else chapter.title,
                sound_prompt=asset["name"],
                production_note=f"素材库：{asset['name']} · {asset.get('license', 'user-provided')}",
                audio_events=[cue],
                audio_versions=[],
                audio_variants=[],
                status="done",
                is_done=1,
            )
            lines.insert(insertion_index, new_line)
            for order, line in enumerate(lines, start=1):
                line.line_order = order
            self.db.add(new_line)
            self.db.flush()
            target_dir = Path(getConfigPath()) / "assets" / str(chapter.id) / "audio"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"id_{new_line.id}_asset_{uuid4().hex[:8]}{source.suffix.lower()}"
            shutil.copy2(source, target)
            new_line.audio_path = str(target)
            self.db.flush()

            timeline_service = TimelineService(self.db)
            if tracks:
                clips = self.db.query(TimelineClipPO).filter(TimelineClipPO.chapter_id == chapter.id).all()
                track = next((track for track in tracks if track.track_type == new_line.track), None)
                if track is None:
                    tracks = timeline_service._ensure_tracks(chapter.project_id, chapter.id)
                    track = next(track for track in tracks if track.track_type == new_line.track)
                clip = timeline_service.add_sound_library_clip(chapter.project_id, chapter.id, new_line, track, clips)
                fingerprint = timeline_service._source_fingerprint(lines)
                for track in tracks:
                    # A pre-existing stale source must remain stale. Updating only
                    # synchronized fingerprints acknowledges our own insertion.
                    if track.source_fingerprint == old_fingerprint:
                        track.source_fingerprint = fingerprint
                        track.revision += 1
            self.db.commit()
            return {
                "line_id": new_line.id,
                "chapter_id": chapter.id,
                "clip_id": clip.id if clip else None,
                "audio_path": str(target),
                "asset_name": asset["name"],
                "duplicate": duplicate,
                "placement_pending": clip is None,
                "start_ms": clip.start_ms if clip else None,
            }
        except Exception:
            self.db.rollback()
            if target:
                target.unlink(missing_ok=True)
            raise

    def delete_user_asset(self, asset_id: str) -> None:
        row = self._get_user(asset_id)
        path = Path(row.path)
        self.db.delete(row)
        self.db.commit()
        path.unlink(missing_ok=True)

    def _get_user(self, asset_id: str) -> SoundLibraryAssetPO:
        try:
            row_id = int(asset_id.removeprefix("user_"))
        except ValueError as exc:
            raise ValueError("用户素材 ID 无效") from exc
        row = self.db.get(SoundLibraryAssetPO, row_id)
        if not row:
            raise ValueError("用户素材不存在")
        return row

    def _builtins(self) -> dict[str, dict[str, Any]]:
        if self._builtin_by_id is not None:
            return self._builtin_by_id
        catalog_path = self.builtin_root / "catalog.json"
        if not catalog_path.is_file():
            raise FileNotFoundError(f"内置素材目录不完整: {catalog_path}")
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        sources = catalog.get("sources", {})
        assets: dict[str, dict[str, Any]] = {}
        for group in catalog.get("groups", []):
            entries = [
                {"file": file_name, "source": group.get("source")}
                for file_name in group.get("files", [])
            ] + group.get("items", [])
            for entry in entries:
                relative_path = entry["file"]
                path = (self.builtin_root / relative_path).resolve()
                if not path.is_file():
                    raise FileNotFoundError(f"内置素材文件不存在: {path}")
                source = sources.get(entry.get("source"), {})
                asset_id = f"builtin_{hashlib.sha1(relative_path.encode('utf-8')).hexdigest()[:16]}"
                duration_ms, sample_rate, channels = self._audio_info(path)
                assets[asset_id] = {
                    "id": asset_id,
                    "name": entry.get("title") or self._title_from_path(path),
                    "category": self._group_category(group.get("id", "foley")),
                    "tags": self._normalize_tags(entry.get("tags") or group.get("tags")),
                    "source_type": "builtin",
                    "license": source.get("license", "CC0-1.0"),
                    "author": source.get("author"),
                    "source_url": source.get("source_url"),
                    "duration_ms": duration_ms,
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "mime_type": mimetypes.guess_type(path.name)[0] or "audio/octet-stream",
                    "path": str(path),
                    "created_at": None,
                }
        self._builtin_by_id = assets
        return assets

    @staticmethod
    def _find_builtin_root() -> Path:
        override = os.environ.get("AURALIS_STOCK_AUDIO_DIR")
        candidates = [
            Path(override).expanduser() if override else None,
            Path(__file__).resolve().parents[3] / "assets" / "audio" / "cc0",
            Path.cwd() / "assets" / "audio" / "cc0",
            Path.cwd().parent / "assets" / "audio" / "cc0",
        ]
        for candidate in candidates:
            if candidate and (candidate / "catalog.json").is_file():
                return candidate.resolve()
        return next(candidate for candidate in candidates if candidate is not None).resolve()

    _audio_info = staticmethod(probe_audio)

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_audio_file(path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"素材文件不存在: {path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError("仅支持 wav/mp3/m4a/ogg/flac 音频素材")
        if path.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError("单个音频素材不能超过 200 MB")

    @staticmethod
    def _normalize_name(name: str) -> str:
        value = re.sub(r"\s+", " ", str(name or "")).strip()
        return value[:255] or "未命名素材"

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str]:
        result: list[str] = []
        for tag in tags or []:
            value = re.sub(r"\s+", " ", str(tag)).strip().lower()[:40]
            if value and value not in result:
                result.append(value)
        return result[:12]

    @staticmethod
    def _normalize_category(category: str | None, allow_empty: bool = False) -> str | None:
        value = (category or "").strip().lower()
        if not value and allow_empty:
            return None
        if value not in CATEGORIES:
            raise ValueError(f"不支持的素材分类: {category}")
        return value

    @staticmethod
    def _group_category(group_id: str) -> str:
        return {
            "supplemental_ambience": "ambience",
            "supplemental_foley": "foley",
        }.get(group_id, group_id if group_id in CATEGORIES else "foley")

    @staticmethod
    def _title_from_path(path: Path) -> str:
        stem = re.sub(r"^sfx100v2_", "", path.stem)
        match = re.fullmatch(r"(.+?)(?:_(\d+))?", stem)
        kind = match.group(1) if match else stem
        number = match.group(2) if match else None
        labels = {
            "air": "气流风声",
            "door": "门开合",
            "footstep": "脚步",
            "footstep_wet": "湿地脚步",
            "footstep_wood": "木地板脚步",
            "glass": "玻璃撞击",
            "hit": "撞击",
            "lock_open": "开锁",
            "loop_ambient": "环境循环",
            "loop_highway": "公路环境",
            "loop_water": "水流循环",
            "switch": "开关",
            "thunder": "雷声",
            "wood_hit": "木材撞击",
        }
        title = labels.get(kind, kind.replace("_", " ").title())
        return f"{title} {number}" if number else title

    @staticmethod
    def _serialize_user(row: SoundLibraryAssetPO) -> dict[str, Any]:
        return {
            "id": f"user_{row.id}",
            "name": row.name,
            "category": row.category,
            "tags": row.tags or [],
            "source_type": "user",
            "license": row.license,
            "author": None,
            "source_url": None,
            "duration_ms": row.duration_ms,
            "sample_rate": row.sample_rate,
            "channels": row.channels,
            "mime_type": row.mime_type,
            "path": row.path,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
