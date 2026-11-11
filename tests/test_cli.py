import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_preview_apply_history_and_undo(self):
        with tempfile.TemporaryDirectory(prefix="pastapronta-cli-") as temporary:
            base = Path(temporary)
            folder = base / "entrada"
            folder.mkdir()
            source = folder / "olá.txt"
            source.write_text("Conteúdo de exemplo", encoding="utf-8")
            def command(*args):
                return subprocess.run([sys.executable, "-X", "utf8", "-m", "pasta_pronta", "--state-dir",
                                       str(base / "estado"), *map(str, args)],
                                      capture_output=True, encoding="utf-8", timeout=20)
            preview = command("organize", folder)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("Somente prévia", preview.stdout)
            self.assertTrue(source.exists())
            applied = command("organize", folder, "--apply")
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse(source.exists())
            batches = json.loads(command("history").stdout)
            self.assertEqual(batches[0]["moved"], 1)
            undone = command("undo", batches[0]["id"], "--apply")
            self.assertEqual(undone.returncode, 0, undone.stderr)
            self.assertEqual(json.loads(undone.stdout)["restored"], 1)
            self.assertEqual(source.read_text(encoding="utf-8"), "Conteúdo de exemplo")

    def test_invalid_folder_has_readable_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([sys.executable, "-X", "utf8", "-m", "pasta_pronta", "--state-dir", temporary,
                                     "scan", str(Path(temporary) / "inexistente")],
                                    capture_output=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Erro:", result.stderr)


if __name__ == "__main__":
    unittest.main()
