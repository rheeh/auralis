import unittest
from types import SimpleNamespace
from sqlalchemy import create_engine, text
from app.db.migrations import apply_schema_migrations, CURRENT_SCHEMA_VERSION

class RuntimeConfigurationTest(unittest.TestCase):
    def test_voice_migration_preserves_description_and_rejects_ambiguity(self):
        engine=create_engine('sqlite:///:memory:')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE voices (id INTEGER PRIMARY KEY, description TEXT)'))
            conn.execute(text("INSERT INTO voices VALUES (1, '角色声 qwen_voice:alice'),(2,'qwen_voice:a cosyvoice_voice:b')"))
        apply_schema_migrations(engine)
        with engine.connect() as conn:
            rows=conn.execute(text('SELECT id, description, provider_voice_id FROM voices ORDER BY id')).all()
        self.assertEqual(rows[0].provider_voice_id,'alice')
        self.assertEqual(rows[0].description,'角色声 qwen_voice:alice')
        self.assertIsNone(rows[1].provider_voice_id)
        from app.core.voice_binding import resolve_voice_key
        with self.assertRaises(ValueError):resolve_voice_key(SimpleNamespace(description=rows[1].description))
        engine.dispose()

    def test_explicit_voice_key_wins_over_legacy_description(self):
        from app.core.voice_binding import resolve_voice_key
        self.assertEqual(resolve_voice_key(SimpleNamespace(provider_voice_id='explicit',description='qwen_voice:old')),'explicit')
