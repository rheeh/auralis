"""Versioned, non-destructive SQLite schema migrations.

The project used to add columns from ``main.py`` on every startup.  Keep the
legacy column definitions here as the first recorded migration, then add new
schema in numbered migrations so a user's existing SQLite file is upgraded in
place and future changes have one auditable entry point.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import Engine, inspect, text


SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
CURRENT_SCHEMA_VERSION = 2


def _table_exists(engine: Engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _columns(engine: Engine, table_name: str) -> set[str]:
    if not _table_exists(engine, table_name):
        return set()
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _add_columns(engine: Engine, table_name: str, definitions: dict[str, str]) -> None:
    if not _table_exists(engine, table_name):
        return
    existing = _columns(engine, table_name)
    with engine.begin() as conn:
        for name, definition in definitions.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))
            logging.info("已添加 %s.%s 字段。", table_name, name)


def _migration_001_legacy_columns(engine: Engine) -> None:
    """Record all columns previously added by startup helpers.

    This is deliberately idempotent: databases created before the migration
    table may already contain any subset of these columns.
    """

    _add_columns(engine, "projects", {
        "prompt_id": "INTEGER",
        "is_precise_fill": "INTEGER DEFAULT 0",
        "project_root_path": "TEXT",
    })
    _add_columns(engine, "lines", {
        "is_done": "INTEGER DEFAULT 0",
        "line_type": "TEXT DEFAULT 'dialogue' NOT NULL",
        "track": "TEXT DEFAULT 'voice' NOT NULL",
        "should_speak": "INTEGER DEFAULT 1 NOT NULL",
        "scene_title": "TEXT",
        "sound_prompt": "TEXT",
        "voice_profile": "TEXT",
        "production_note": "TEXT",
        "audio_events": "TEXT",
        "audio_versions": "TEXT",
        "active_audio_version_id": "TEXT",
        "audio_variants": "TEXT",
        "active_audio_variant_id": "TEXT",
    })
    _add_columns(engine, "llm_provider", {"custom_params": "TEXT"})
    _add_columns(engine, "tts_provider", {
        "provider_type": "TEXT DEFAULT 'cloud' NOT NULL",
        "model": "TEXT",
        "custom_params": "TEXT",
    })
    _add_columns(engine, "roles", {
        "avatar_path": "TEXT",
        "role_importance": "TEXT DEFAULT 'supporting' NOT NULL",
        "tts_route": "TEXT DEFAULT 'auto' NOT NULL",
        "edge_voice": "TEXT",
    })
    _add_columns(engine, "adaptation_runs", {
        "session_id": "TEXT",
        "is_conversational": "INTEGER DEFAULT 0 NOT NULL",
        "source_revision": "INTEGER DEFAULT 1 NOT NULL",
        "draft_revision": "INTEGER DEFAULT 1 NOT NULL",
        "review_json": "TEXT",
        "committed_at": "DATETIME",
    })
    _add_columns(engine, "audio_tasks", {
        "review_status": "TEXT DEFAULT 'pending' NOT NULL",
        "review_note": "TEXT",
    })

    # Preserve the old startup behavior for existing LLM provider rows.
    if _table_exists(engine, "llm_provider") and "custom_params" in _columns(engine, "llm_provider"):
        default_json = json.dumps({
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "top_p": 0.9,
        }, ensure_ascii=False)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE llm_provider SET custom_params = :value WHERE custom_params IS NULL"),
                {"value": default_json},
            )


def _migration_002_timeline_foundation(engine: Engine) -> None:
    """Create the audio-asset and timeline tables without touching old data."""

    # Import lazily to avoid a models -> database -> migrations import cycle.
    from app.models.po import AudioAssetPO, TimelineClipPO, TimelineTrackPO

    for model in (AudioAssetPO, TimelineTrackPO, TimelineClipPO):
        model.__table__.create(bind=engine, checkfirst=True)


MIGRATIONS = {
    1: _migration_001_legacy_columns,
    2: _migration_002_timeline_foundation,
}


def apply_schema_migrations(engine: Engine) -> None:
    """Apply each missing migration exactly once and verify the version table."""

    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} ("
            "version INTEGER PRIMARY KEY, applied_at DATETIME NOT NULL)"
        ))

    with engine.connect() as conn:
        applied = {
            row[0]
            for row in conn.execute(text(f"SELECT version FROM {SCHEMA_MIGRATIONS_TABLE}"))
        }
    for version in range(1, CURRENT_SCHEMA_VERSION + 1):
        if version in applied:
            continue
        migration = MIGRATIONS[version]
        logging.info("执行 SQLite schema migration %s。", version)
        migration(engine)
        with engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version, applied_at) VALUES (:version, :applied_at)"),
                {"version": version, "applied_at": datetime.now(timezone.utc)},
            )

    with engine.connect() as conn:
        current = conn.execute(
            text(f"SELECT COALESCE(MAX(version), 0) FROM {SCHEMA_MIGRATIONS_TABLE}")
        ).scalar_one()
    if current != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(f"SQLite schema migration 不完整: 当前 {current}, 期望 {CURRENT_SCHEMA_VERSION}")


def migrate_workflow_schema(engine: Engine) -> None:
    """Backward-compatible alias for callers outside the application entrypoint."""

    apply_schema_migrations(engine)
