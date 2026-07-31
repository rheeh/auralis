import os
import tempfile
import unittest
from unittest.mock import patch

import soundfile as sf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.migrations import apply_schema_migrations
from app.models.po import SoundLibraryAssetPO
from app.services.sound_library_service import SoundLibraryService


class SoundLibraryServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        apply_schema_migrations(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = tempfile.TemporaryDirectory()
        builtin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "audio", "cc0"))
        self.service = SoundLibraryService(self.session, builtin_root=builtin_root)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()
        self.config_dir.cleanup()

    def _wav(self, name="custom.wav"):
        path = os.path.join(self.temp_dir.name, name)
        sf.write(path, [0.0] * 8000, 16000)
        return path

    def test_builtin_catalog_is_complete_and_filterable(self):
        assets = self.service.list_assets(source_type="builtin")
        self.assertEqual(len(assets), 32)
        self.assertTrue(all(asset["license"] == "CC0-1.0" for asset in assets))
        self.assertTrue(all(asset["duration_ms"] > 0 for asset in assets))
        self.assertTrue(all(os.path.isfile(asset["path"]) for asset in assets))
        weather = self.service.list_assets(source_type="builtin", category="weather")
        self.assertEqual({asset["category"] for asset in weather}, {"weather"})
        self.assertTrue(self.service.list_assets(source_type="builtin", keyword="thunder"))
        self.assertEqual(
            [asset["name"] for asset in self.service.list_assets(source_type="builtin", keyword="火焰")],
            ["火焰燃烧"],
        )

    def test_user_import_is_copied_deduplicated_and_deletable(self):
        source = self._wav()
        with patch("app.services.sound_library_service.getConfigPath", return_value=self.config_dir.name):
            imported = self.service.import_path(source, "自定义提示音", "foley", ["提示", "短音"])
            duplicate = self.service.import_path(source, "另一个名字", "foley", [])

        self.assertEqual(imported["id"], duplicate["id"])
        self.assertEqual(self.session.query(SoundLibraryAssetPO).count(), 1)
        self.assertNotEqual(os.path.abspath(source), imported["path"])
        self.assertTrue(os.path.isfile(imported["path"]))
        self.assertEqual(imported["duration_ms"], 500)
        self.assertEqual(imported["tags"], ["提示", "短音"])

        self.service.delete_user_asset(imported["id"])
        self.assertEqual(self.session.query(SoundLibraryAssetPO).count(), 0)
        self.assertFalse(os.path.exists(imported["path"]))

    def test_invalid_category_and_builtin_delete_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.import_path(self._wav(), category="unknown")
        builtin = self.service.list_assets(source_type="builtin")[0]
        self.assertTrue(self.service.resolve_path(builtin["id"]).is_file())
        with self.assertRaises(ValueError):
            self.service.delete_user_asset(builtin["id"])


if __name__ == "__main__":
    unittest.main()
