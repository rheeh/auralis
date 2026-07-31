from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import soundfile as sf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import getConfigPath
from app.models.po import SoundLibraryAssetPO


SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
CATEGORIES = {"ambience", "weather", "doors", "footsteps", "impacts", "foley", "bgm"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024


class SoundLibraryService:
    def __init__(self, db: Session, builtin_root: str | Path | None = None):
        self.db = db
        self.builtin_root = Path(builtin_root) if builtin_root else self._find_builtin_root()
        self._builtin_by_id: dict[str, dict[str, Any]] | None = None

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

    @staticmethod
    def _audio_info(path: Path) -> tuple[int, int | None, int | None]:
        try:
            info = sf.info(str(path))
            duration_ms = round((info.frames / info.samplerate) * 1000) if info.samplerate else 0
            return duration_ms, int(info.samplerate or 0) or None, int(info.channels or 0) or None
        except (RuntimeError, ValueError):
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                raise ValueError(f"无法解析音频文件: {path.name}")
            try:
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                duration = float(json.loads(result.stdout).get("format", {}).get("duration") or 0)
                return round(duration * 1000), None, None
            except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"无法解析音频文件: {path.name}") from exc

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
