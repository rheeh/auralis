import logging

from sqlalchemy import Engine, inspect, text


ADAPTATION_RUN_COLUMNS = {
    "session_id": "TEXT",
    "is_conversational": "INTEGER DEFAULT 0 NOT NULL",
    "source_revision": "INTEGER DEFAULT 1 NOT NULL",
    "draft_revision": "INTEGER DEFAULT 1 NOT NULL",
    "review_json": "TEXT",
    "committed_at": "DATETIME",
}

AUDIO_TASK_COLUMNS = {
    "review_status": "TEXT DEFAULT 'pending' NOT NULL",
    "review_note": "TEXT",
}

ROLE_COLUMNS = {
    "avatar_path": "TEXT",
}


def migrate_workflow_schema(engine: Engine) -> None:
    """Idempotently upgrade existing SQLite databases without deleting user data."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "adaptation_runs" not in table_names:
        return

    existing = {column["name"] for column in inspector.get_columns("adaptation_runs")}
    with engine.begin() as conn:
        for column_name, column_definition in ADAPTATION_RUN_COLUMNS.items():
            if column_name in existing:
                continue
            conn.execute(text(f"ALTER TABLE adaptation_runs ADD COLUMN {column_name} {column_definition}"))
            logging.info("已添加 adaptation_runs.%s 字段。", column_name)

    verified = {column["name"] for column in inspect(engine).get_columns("adaptation_runs")}
    missing = set(ADAPTATION_RUN_COLUMNS) - verified
    if missing:
        raise RuntimeError(f"工作流数据库迁移不完整: {', '.join(sorted(missing))}")

    if "audio_tasks" in table_names:
        audio_existing = {column["name"] for column in inspect(engine).get_columns("audio_tasks")}
        with engine.begin() as conn:
            for column_name, column_definition in AUDIO_TASK_COLUMNS.items():
                if column_name not in audio_existing:
                    conn.execute(text(f"ALTER TABLE audio_tasks ADD COLUMN {column_name} {column_definition}"))
                    logging.info("已添加 audio_tasks.%s 字段。", column_name)

    if "roles" in table_names:
        role_existing = {column["name"] for column in inspector.get_columns("roles")}
        with engine.begin() as conn:
            for column_name, column_definition in ROLE_COLUMNS.items():
                if column_name not in role_existing:
                    conn.execute(text(f"ALTER TABLE roles ADD COLUMN {column_name} {column_definition}"))
                    logging.info("已添加 roles.%s 字段。", column_name)
