import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text

from app.db.migrations import ADAPTATION_RUN_COLUMNS, CHAT_SESSION_COLUMNS, migrate_workflow_schema


class WorkflowMigrationTest(unittest.TestCase):
    def test_phase_zero_columns_are_added_and_backfilled_idempotently(self):
        with tempfile.TemporaryDirectory() as tempdir:
            engine = create_engine(f"sqlite:///{tempdir}/legacy.sqlite3")
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE adaptation_runs (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL)"))
                conn.execute(text("CREATE TABLE chat_sessions (id TEXT PRIMARY KEY, project_id INTEGER NOT NULL)"))
                conn.execute(text("INSERT INTO adaptation_runs (id, project_id) VALUES (1, 1)"))
                conn.execute(text("INSERT INTO chat_sessions (id, project_id) VALUES ('sess_legacy', 1)"))

            migrate_workflow_schema(engine)
            migrate_workflow_schema(engine)

            inspector = inspect(engine)
            run_columns = {column["name"] for column in inspector.get_columns("adaptation_runs")}
            session_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
            self.assertTrue(set(ADAPTATION_RUN_COLUMNS).issubset(run_columns))
            self.assertTrue(set(CHAT_SESSION_COLUMNS).issubset(session_columns))
            with engine.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT source_kind FROM adaptation_runs WHERE id = 1")).scalar_one(), "novel")
                row = conn.execute(text("SELECT source_type, adaptation_mode FROM chat_sessions WHERE id = 'sess_legacy'")).one()
                self.assertEqual(tuple(row), ("novel", "drama"))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
