"""Actual-worker status, frozen checkpoint counts, disk and queue ordering."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from benchmarks.expanded.comparator_first import TOOLS
from benchmarks.expanded.comparator_status_monitor import (
    ARCHIVE, MIN_FREE, ORIGINAL, PER_ACTIVE, REAL, SOURCES, SYNTH,
    snapshot, write_atomic,
)


class ComparatorStatusMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.real = self.root / REAL.relative_to(Path("/workspace"))
        self.synth = self.root / SYNTH.relative_to(Path("/workspace"))
        self.real.mkdir(parents=True)
        self.synth.mkdir(parents=True)
        self.free = 20 * 1024**3

    def manifest(self, tag):
        path = self.real if tag == "physical" else self.synth
        samples = 198 if tag == "physical" else 400
        doc = {"source_commit": SOURCES[tag], "expected_samples": samples,
               "expected_arms": samples * 6, "qualified": False,
               "images": {name: str(i) * 64 for i, name in
                          enumerate(TOOLS, start=1)}}
        if tag == "physical":
            doc["original_inputs"] = {
                f"sample{i:03d}": "original-source-sha"
                for i in range(samples) }
        else:
            doc["truth_validation"] = {"valid": True}
        (path / "run_manifest.json").write_text(json.dumps(doc))

    def add(self, tag, assembler, sample, status="success"):
        path = self.real if tag == "physical" else self.synth
        row = {"assembler": assembler,
               "sample" if tag == "physical" else "id": sample}
        if tag == "physical":
            row["status"] = status
        else:
            row["result"] = {"status": status}
        with (path / "results.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")

    def snapshot(self, active=None):
        if active is None:
            active = {"physical": [], "synthetic": []}
        with patch("benchmarks.expanded.comparator_status_monitor"
                   ".shutil.disk_usage",
                   return_value=SimpleNamespace(free=self.free)):
            return snapshot(self.root, running=active)

    def prerequisites(self):
        for original in (ORIGINAL, ARCHIVE):
            file = self.root / original.relative_to(Path("/workspace"))
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('{"success":true}\n')

    def test_supervisor_up_without_actual_worker_is_queued(self):
        statuses = self.snapshot()
        self.assertEqual(statuses["physical"]["execution_state"], "queued")
        self.assertEqual(statuses["synthetic"]["execution_state"], "queued")
        self.assertEqual(statuses["physical"]["terminal_arms"], 0)
        self.assertEqual(statuses["synthetic"]["terminal_arms"], 0)
        self.assertEqual(statuses["disk_headroom_at_ten_workers"],
                         self.free - MIN_FREE - 10 * PER_ACTIVE)

    def test_verified_source_and_process_is_executing(self):
        self.prerequisites()
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        self.add("physical", "iva", "sample_2", "failed")
        data = self.snapshot({"physical": [123], "synthetic": []})
        self.assertEqual(data["physical"]["execution_state"], "executing")
        self.assertEqual(data["physical"]["worker_pids"], [123])
        self.assertEqual(data["physical"]["successful"], 1)
        self.assertEqual(data["physical"]["failed"], 1)
        self.assertEqual(data["synthetic"]["execution_state"], "queued")
        self.assertIn("fixed physical comparators",
                      data["synthetic"]["reason"])

    def test_disk_pause_is_distinct_from_finished_and_queued(self):
        self.prerequisites()
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        self.free = MIN_FREE
        data = self.snapshot()
        self.assertEqual(data["physical"]["execution_state"], "paused_low_disk")
        self.assertEqual(data["physical"]["terminal_arms"], 1)
        self.assertLess(data["disk_headroom_at_ten_workers"], 0)

    def test_no_restart_of_journal_counts_when_worker_missing(self):
        self.prerequisites()
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        first = self.snapshot({"physical": [4321], "synthetic": []})
        second = self.snapshot({"physical": [], "synthetic": []})
        self.assertEqual(first["physical"]["terminal_arms"], 1)
        self.assertEqual(second["physical"]["terminal_arms"], 1)
        self.assertEqual(second["physical"]["execution_state"],
                         "ready_or_retrying")

    def test_synthetic_stays_queued_until_real_completion_marker(self):
        self.prerequisites()
        self.manifest("synthetic")
        self.add("synthetic", "iva", "s001")
        data = self.snapshot({"physical": [], "synthetic": []})
        self.assertEqual(data["synthetic"]["execution_state"], "queued")
        marker = self.real / "attempt-finished.json"
        marker.write_text('{"arms":1188,"failed_arms":0}\n')
        data = self.snapshot({"physical": [], "synthetic": [456]})
        self.assertEqual(data["synthetic"]["execution_state"], "executing")

    def test_duplicate_or_unknown_source_refused(self):
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        self.add("physical", "iva", "sample_1")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.snapshot()
        (self.real / "results.jsonl").unlink()
        doc = json.loads((self.real / "run_manifest.json").read_text())
        doc["source_commit"] = "not-source"
        (self.real / "run_manifest.json").write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "source"):
            self.snapshot()

    def test_partial_journal_does_not_misreport_zero(self):
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        with (self.real / "results.jsonl").open("a") as journal:
            journal.write('{"incomplete":')
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.snapshot()

    def test_completed_requires_consistent_terminal_marker(self):
        self.manifest("physical")
        for name in TOOLS:
            for i in range(198):
                self.add("physical", name, f"sample{i:03d}")
        self.prerequisites()
        data = self.snapshot()
        self.assertEqual(data["physical"]["terminal_arms"], 1188)
        self.assertEqual(data["physical"]["execution_state"],
                         "ready_or_retrying")
        (self.real / "attempt-finished.json").write_text(
            '{"arms":1188,"failed_arms":0}\n')
        self.assertEqual(self.snapshot()["physical"]["execution_state"],
                         "completed")
        (self.real / "attempt-finished.json").write_text(
            '{"arms":1188,"failed_arms":1}\n')
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.snapshot()

    def test_atomic_status_does_not_mutate_benchmark_journal(self):
        out = self.root / "status.json"
        self.manifest("physical")
        self.add("physical", "iva", "sample_1")
        before = (self.real / "results.jsonl").read_bytes()
        payload = self.snapshot()
        write_atomic(out, payload)
        self.assertEqual(json.loads(out.read_text())["physical"]["terminal_arms"], 1)
        self.assertEqual((self.real / "results.jsonl").read_bytes(), before)
        self.assertFalse(out.with_name("status.json.partial").exists())


if __name__ == "__main__":
    unittest.main()
