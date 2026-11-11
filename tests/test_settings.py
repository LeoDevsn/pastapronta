import tempfile
import unittest
from pathlib import Path

from pasta_pronta import settings


class SettingsTests(unittest.TestCase):
    def test_preferences_roundtrip_and_corrupt_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(settings.load(directory), {})
            settings.save(directory, "C:/Documentação", True, False)
            self.assertEqual(settings.load(directory), {"folder": "C:/Documentação", "recursive": True, "by_month": False})
            (directory / "preferencias.json").write_text("invalid", encoding="utf-8")
            self.assertEqual(settings.load(directory), {})
