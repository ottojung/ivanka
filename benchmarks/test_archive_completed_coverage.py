"""Crash, integrity and safety tests for completed historical coverage archival."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from benchmarks.maintenance.archive_completed_coverage import run


class CompletedCoverageArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "historical"
        self.audit = Path(self.temp.name) / "audit"
        self.root.mkdir()
        self.cutoff = time.time() + 600

    def fixture(self, count=1):
        records = []
        for index in range(count):
            name = f"case-{index}"
            records.append({"id": name})
            arm = self.root / name / "iva"
            maps = arm / "coverage_maps"
            maps.mkdir(parents=True, exist_ok=True)
            (maps / "map.txt").write_bytes(b"A" * 6000 + bytes([index]))
            (arm / "execution.json").write_text('{"status":"success"}\n')
            (arm / "conseq.csv").write_bytes(b"reference,consensus\nHXB2,ACTG\n")
        raw = "".join(json.dumps(x) + "\n" for x in records).encode()
        (self.root / "results.jsonl").write_bytes(raw)
        (self.root / "run_manifest.json").write_text('{"qualified":false}\n')
        (self.root / "attempt_summary.json").write_text(json.dumps({
            "cases_attempted": count, "expected_cases": count,
            "result_sha256": sha256(raw).hexdigest()}) + "\n")

    def test_archives_losslessly_and_preserves_final_and_journal(self):
        self.fixture(2)
        before = (self.root / "results.jsonl").read_bytes()
        final = self.root / "case-0" / "iva" / "conseq.csv"
        original_final = final.read_bytes()
        self.assertEqual(run(self.root, self.audit, 2, self.cutoff, 1), (1, 2))
        self.assertFalse((self.audit / "completed.json").exists())
        self.assertEqual(run(self.root, self.audit, 2, self.cutoff), (2, 2))
        self.assertEqual(run(self.root, self.audit, 2, self.cutoff), (2, 2))
        self.assertFalse((final.parent / "coverage_maps").exists())
        self.assertTrue((final.parent / "coverage_maps.tar.gz").is_file())
        self.assertEqual(final.read_bytes(), original_final)
        self.assertEqual((self.root / "results.jsonl").read_bytes(), before)
        self.assertEqual(json.loads((self.audit / "completed.json").read_text())
                         ["items"], 2)

    def test_crash_after_archive_is_idempotently_recoverable(self):
        self.fixture()
        folder = self.root / "case-0" / "iva" / "coverage_maps"
        with patch("benchmarks.maintenance.archive_completed_coverage.shutil.rmtree",
                   side_effect=RuntimeError("simulated crash")):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                run(self.root, self.audit, 1, self.cutoff)
        self.assertTrue(folder.is_dir())
        self.assertTrue(folder.with_name("coverage_maps.tar.gz").is_file())
        self.assertEqual(run(self.root, self.audit, 1, self.cutoff), (1, 1))
        self.assertFalse(folder.exists())

    def test_missing_completion_and_tampered_journal_fail_closed(self):
        self.fixture()
        (self.root / "attempt_summary.json").unlink()
        with self.assertRaises(ValueError):
            run(self.root, self.audit, 1, self.cutoff)
        self.fixture()
        (self.root / "results.jsonl").write_text('{"id":"different"}\n')
        with self.assertRaises(ValueError):
            run(self.root, self.audit, 1, self.cutoff)
        self.assertTrue((self.root / "case-0/iva/coverage_maps").is_dir())

    def test_symlink_cannot_be_archived_or_removed(self):
        self.fixture()
        maps = self.root / "case-0" / "iva" / "coverage_maps"
        (maps / "outside").symlink_to(self.root / "run_manifest.json")
        with self.assertRaisesRegex(ValueError, "symlink"):
            run(self.root, self.audit, 1, self.cutoff)
        self.assertTrue(maps.exists())
        self.assertTrue((self.root / "run_manifest.json").is_file())

    def test_recent_source_cannot_be_archived(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, "unfrozen"):
            run(self.root, self.audit, 1, time.time() - 500)
        self.assertTrue((self.root / "case-0/iva/coverage_maps").is_dir())


if __name__ == "__main__":
    unittest.main()
