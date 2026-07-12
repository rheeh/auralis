from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.core.config import getConfigPath


BACKUP_RELATIVE_PATH = os.path.join("backups", "provider_config_snapshots.jsonl")


def snapshot_provider_config(provider_kind: str, action: str, provider: Any) -> str | None:
    """Write a local recovery snapshot for LLM/TTS provider configs.

    The snapshot intentionally keeps the full API key in the user's local config
    directory so accidental UI overwrites/deletes can be recovered. Do not print
    these records to logs or API responses.
    """
    if provider is None:
        return None

    try:
        backup_path = os.path.join(getConfigPath(), BACKUP_RELATIVE_PATH)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        provider_data = _provider_to_dict(provider)
        record = {
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "provider_kind": provider_kind,
            "action": action,
            "api_key_len": len(provider_data.get("api_key") or ""),
            "api_key_masked": _mask_secret(provider_data.get("api_key")),
            "provider": provider_data,
        }
        with open(backup_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")
        try:
            os.chmod(backup_path, 0o600)
        except OSError:
            pass
        return backup_path
    except Exception:
        logging.warning("Provider config snapshot failed", exc_info=True)
        return None


def _provider_to_dict(provider: Any) -> dict[str, Any]:
    if is_dataclass(provider):
        data = asdict(provider)
    elif hasattr(provider, "__table__"):
        data = {column.name: getattr(provider, column.name) for column in provider.__table__.columns}
    elif isinstance(provider, dict):
        data = dict(provider)
    else:
        data = {key: value for key, value in provider.__dict__.items() if not key.startswith("_")}
    return {key: _json_default(value) for key, value in data.items()}


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _mask_secret(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"
