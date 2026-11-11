"""Testes com arquivos temporários reais: prevenção de perda e automação."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pasta_pronta.core import History, Monitor, export_csv, fingerprint, scan


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pastapronta-test-")
        self.base = Path(self.temp.name)
        self.root = self.base / "entrada"
        self.root.mkdir()
        self.history = History(self.base / "estado")

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, content=b"conteudo"):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_scan_is_read_only_and_detects_content_duplicates(self):
        a = self.file("relatorio.txt", b"igual")
        b = self.file("foto.png", b"igual")
        self.file("outra.txt", b"diferente")
        self.file("download.crdownload")
        self.file("~$temporario.docx")
        self.file(".oculto")
        self.file("sub/anotacao.txt")
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        plan = scan(self.root)
        self.assertEqual(len(plan.items), 3)
        self.assertEqual(plan.duplicates, 1)
        self.assertEqual(plan.skipped, 3)
        self.assertEqual(sorted(p.relative_to(self.root) for p in self.root.rglob("*")), before)
        self.assertTrue(a.exists() and b.exists())
        self.assertFalse((self.root / "Organizados").exists())

    def test_recursive_excludes_output_and_disambiguates_names(self):
        existing = self.file("Organizados/Documentos/a.txt", b"existente")
        self.file("primeira/a.txt", b"um")
        self.file("segunda/a.txt", b"dois")
        plan = scan(self.root, recursive=True)
        self.assertEqual(len(plan.items), 2)
        self.assertEqual([i.destination.name for i in plan.items], ["a (2).txt", "a (3).txt"])
        result = self.history.execute(plan)
        self.assertEqual(result["moved"], 2)
        self.assertEqual(existing.read_bytes(), b"existente")
        self.assertEqual(scan(self.root, recursive=True).items, [])

    def test_move_and_undo_restore_exact_bytes_and_timestamp(self):
        a = self.file("arquivo.txt", b"\x00\xff\x10 bytes\n")
        original_mtime = a.stat().st_mtime_ns
        digest = fingerprint(a)
        plan = scan(self.root)
        result = self.history.execute(plan)
        self.assertEqual(result["errors"], [])
        self.assertFalse(a.exists())
        self.assertEqual(fingerprint(plan.items[0].destination), digest)
        self.assertEqual(self.history.batches()[0]["moved"], 1)
        self.assertEqual(self.history.batches()[0]["errors"], 0)
        restored = self.history.undo(result["id"])
        self.assertEqual(restored, {"restored": 1, "errors": []})
        self.assertEqual(fingerprint(a), digest)
        self.assertEqual(a.stat().st_mtime_ns, original_mtime)
        self.assertEqual(self.history.undo(result["id"])["restored"], 0)

    def test_changed_source_is_not_moved(self):
        source = self.file("arquivo.txt", b"antes")
        plan = scan(self.root)
        source.write_bytes(b"modificado")
        result = self.history.execute(plan)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(source.read_bytes(), b"modificado")

    def test_changed_content_with_same_metadata_is_not_moved(self):
        source = self.file("arquivo.txt", b"antes")
        plan = scan(self.root)
        source.write_bytes(b"depoi")
        os.utime(source, ns=(source.stat().st_atime_ns, plan.items[0].mtime_ns))
        result = self.history.execute(plan)
        self.assertEqual(result["moved"], 0)
        self.assertTrue(source.exists())

    def test_destination_created_after_scan_is_never_overwritten(self):
        source = self.file("arquivo.txt", b"original")
        plan = scan(self.root)
        destination = plan.items[0].destination
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"novo arquivo")
        result = self.history.execute(plan)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(destination.read_bytes(), b"novo arquivo")
        self.assertEqual(source.read_bytes(), b"original")

    def test_undo_preserves_modified_destination(self):
        self.file("arquivo.txt", b"original")
        plan = scan(self.root)
        result = self.history.execute(plan)
        plan.items[0].destination.write_bytes(b"edicao posterior")
        undo = self.history.undo(result["id"])
        self.assertEqual(undo["restored"], 0)
        self.assertEqual(len(undo["errors"]), 1)
        self.assertEqual(plan.items[0].destination.read_bytes(), b"edicao posterior")
        self.assertEqual(self.history.batches()[0]["moved"], 1)
        self.assertEqual(self.history.batches()[0]["errors"], 1)

    def test_undo_can_retry_after_conflict_is_resolved(self):
        source = self.file("arquivo.txt", b"original")
        plan = scan(self.root)
        result = self.history.execute(plan)
        source.write_bytes(b"outro arquivo")
        undo = self.history.undo(result["id"])
        self.assertEqual(undo["restored"], 0)
        self.assertEqual(source.read_bytes(), b"outro arquivo")
        source.rename(self.root / "outro.txt")
        self.assertEqual(self.history.undo(result["id"])["restored"], 1)
        self.assertEqual(source.read_bytes(), b"original")

    def test_copy_failure_keeps_original_and_removes_partial_copy(self):
        source = self.file("arquivo.txt", b"original")
        plan = scan(self.root)
        with patch("pasta_pronta.core.shutil.copyfileobj", side_effect=OSError("Disco cheio")):
            result = self.history.execute(plan)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(source.read_bytes(), b"original")
        self.assertFalse(plan.items[0].destination.exists())

    def test_undo_recovers_pending_action_after_interruption(self):
        source = self.file("arquivo.txt", b"original")
        result = self.history.execute(scan(self.root))
        with self.history.connect() as db:
            db.execute("UPDATE actions SET status = 'pending' WHERE batch_id = ?", (result["id"],))
        self.assertEqual(self.history.undo(result["id"])["restored"], 1)
        self.assertEqual(source.read_bytes(), b"original")

    def test_monitor_requires_two_stable_observations(self):
        source = self.file("arquivo.txt", b"primeira versao")
        monitor = Monitor(self.root, self.history, interval=1, settle=0)
        self.assertEqual(monitor.tick()["moved"], 0)
        source.write_bytes(b"segunda versao")
        self.assertEqual(monitor.tick()["moved"], 0)
        self.assertTrue(source.exists())
        self.assertEqual(monitor.tick()["moved"], 1)
        self.assertFalse(source.exists())
        self.assertEqual(monitor.tick()["moved"], 0)

    def test_monitor_ignores_recent_and_partial_files(self):
        self.file("novo.txt")
        self.file("download.part")
        monitor = Monitor(self.root, self.history, interval=1, settle=10)
        self.assertEqual(monitor.tick()["moved"], 0)
        self.assertEqual(monitor.tick()["moved"], 0)
        old = 1_600_000_000
        os.utime(self.root / "novo.txt", (old, old))
        self.assertEqual(monitor.tick()["moved"], 0)
        self.assertEqual(monitor.tick()["moved"], 1)
        self.assertTrue((self.root / "download.part").exists())

    def test_stopped_monitor_does_not_execute(self):
        source = self.file("arquivo.txt")
        monitor = Monitor(self.root, self.history, settle=0)
        monitor.tick()
        monitor.stop()
        self.assertEqual(monitor.tick()["moved"], 0)
        self.assertTrue(source.exists())

    def test_monitor_run_organizes_and_stops_cleanly(self):
        self.file("automatico.txt", b"feito sem cliques")
        finished = threading.Event()
        monitor = Monitor(self.root, self.history, interval=0.05, settle=0,
                          notify=lambda _message: finished.set())
        thread = threading.Thread(target=monitor.run)
        thread.start()
        try:
            self.assertTrue(finished.wait(5), "O monitor não processou o arquivo")
        finally:
            monitor.stop()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        target = self.root / "Organizados" / "Documentos" / "automatico.txt"
        self.assertEqual(target.read_bytes(), b"feito sem cliques")

    def test_month_is_based_on_file_modification_date(self):
        source = self.file("arquivo.txt")
        plan = scan(self.root, by_month=True)
        from datetime import datetime
        month = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y/%m")
        self.assertEqual(plan.items[0].destination, self.root / "Organizados" / "Documentos" / month / "arquivo.txt")

    def test_csv_is_utf8_and_exclusive(self):
        self.file("documentação.txt")
        report = self.base / "relatório.csv"
        export_csv(scan(self.root), report)
        content = report.read_text(encoding="utf-8-sig")
        self.assertIn("documentação.txt", content)
        with self.assertRaises(FileExistsError):
            export_csv(scan(self.root), report)

    def test_export_neutralizes_formula_in_duplicate_name(self):
        self.file("=formula.txt", b"igual")
        self.file("z.txt", b"igual")
        report = self.base / "report.csv"
        export_csv(scan(self.root), report)
        self.assertIn("'=formula.txt", report.read_text(encoding="utf-8-sig"))

    def test_future_mtime_is_included_in_manual_scan(self):
        source = self.file("futuro.txt")
        os.utime(source, (4_000_000_000, 4_000_000_000))
        self.assertEqual(len(scan(self.root).items), 1)

    def test_symlink_source_is_ignored_when_supported(self):
        source = self.file("arquivo.txt")
        try:
            (self.root / "link.txt").symlink_to(source)
        except OSError:
            self.skipTest("Sistema não autoriza criação de symlinks nesta sessão")
        self.assertEqual(len(scan(self.root).items), 1)

    def test_destination_symlink_directory_is_rejected_when_supported(self):
        self.file("arquivo.txt")
        outside = self.base / "fora"
        outside.mkdir()
        try:
            (self.root / "Organizados").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Sistema não autoriza criação de symlinks nesta sessão")
        plan = scan(self.root)
        self.assertEqual(plan.items, [])
        self.assertTrue(plan.warnings)
        self.assertEqual(list(outside.iterdir()), [])

    def test_no_empty_batch_or_unknown_undo(self):
        self.assertEqual(self.history.execute(scan(self.root))["moved"], 0)
        self.assertEqual(self.history.batches(), [])
        with self.assertRaises(ValueError):
            self.history.undo("inexistente")

    def test_internal_history_files_cannot_be_moved(self):
        nested_history = History(self.root / "estado-interno")
        marker = nested_history.directory / "arquivo-interno.txt"
        marker.write_text("preservar", encoding="utf-8")
        result = nested_history.execute(scan(self.root, recursive=True))
        self.assertEqual(result["moved"], 0)
        self.assertTrue(result["errors"])
        self.assertEqual(marker.read_text(encoding="utf-8"), "preservar")


if __name__ == "__main__":
    unittest.main()
