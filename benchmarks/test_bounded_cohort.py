"""Focused tests for fail-fast, bounded full-cohort scheduling."""

import threading
import time
import unittest

from bounded_cohort import execute_bounded


class BoundedCohortTests(unittest.TestCase):
    def test_full_success_runs_every_sample_with_bounded_parallelism(self):
        rows = [{"sample": str(i)} for i in range(9)]
        started, finished = [], []
        lock = threading.Lock()
        active = 0
        maximum = 0

        def worker(row):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.005)
            with lock:
                active -= 1
            return dict(sample=row["sample"], failed=False)

        records, stopped = execute_bounded(
            rows, 3, worker, lambda r: started.append(r["sample"]),
            lambda r: finished.append(r["sample"]),
            lambda name, exc: dict(sample=name, failed=True),
            stop_on_failure=True)
        self.assertFalse(stopped)
        self.assertEqual(set(started), {str(i) for i in range(9)})
        self.assertEqual(set(finished), set(started))
        self.assertEqual(len(records), 9)
        self.assertLessEqual(maximum, 3)

    def test_failure_prevents_new_samples_and_drains_active_ones(self):
        rows = [{"sample": str(i)} for i in range(8)]
        started, finished = [], []

        def worker(row):
            if row["sample"] == "1":
                time.sleep(0.025)
            return dict(sample=row["sample"], failed=row["sample"] == "0")

        records, stopped = execute_bounded(
            rows, 2, worker, lambda r: started.append(r["sample"]),
            lambda r: finished.append(r["sample"]),
            lambda name, exc: dict(sample=name, failed=True),
            stop_on_failure=True)
        self.assertTrue(stopped)
        self.assertEqual(set(started), {"0", "1"})
        self.assertEqual(set(finished), {"0", "1"})
        self.assertEqual(len(records), 2)

    def test_exception_is_recorded_and_stops_strict_run(self):
        rows = [{"sample": str(i)} for i in range(5)]
        errors = []

        def worker(row):
            if row["sample"] == "0":
                raise RuntimeError("authentic failure")
            time.sleep(0.02)
            return dict(sample=row["sample"], failed=False)

        def on_error(name, exc):
            errors.append((name, str(exc)))
            return dict(sample=name, failed=True, status="error")

        records, stopped = execute_bounded(
            rows, 1, worker, lambda r: None, lambda r: None,
            on_error, stop_on_failure=True)
        self.assertTrue(stopped)
        self.assertEqual(len(records), 1)
        self.assertEqual(errors, [("0", "authentic failure")])

    def test_non_strict_mode_continues_after_failure(self):
        rows = [{"sample": str(i)} for i in range(5)]
        records, stopped = execute_bounded(
            rows, 2,
            lambda r: dict(sample=r["sample"], failed=r["sample"] == "0"),
            lambda r: None, lambda r: None,
            lambda name, exc: dict(sample=name, failed=True),
            stop_on_failure=False)
        self.assertFalse(stopped)
        self.assertEqual(len(records), 5)



class StrictRunnerIntegrationTests(unittest.TestCase):
    def test_failed_pair_stops_new_containers_and_cannot_qualify(self):
        import csv
        import importlib.util
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        path = Path(__file__).with_name("podman_full_micall.py")
        spec = importlib.util.spec_from_file_location("strict_runner", path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "manifest.tsv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["sample"],
                                        delimiter="\t")
                writer.writeheader()
                writer.writerows({"sample": f"S{i}"} for i in range(198))
            (root / "hxb2.fasta").write_text(">HXB2\nACGT\n")
            results = root / "results"
            calls = []

            def fake_sample(row, *args, **kwargs):
                calls.append(row["sample"])
                if row["sample"] == "S1":
                    time.sleep(0.025)
                return {"sample": row["sample"], "status": "finished",
                        "failed": row["sample"] == "S0"}

            def fake_image_id(image):
                return (runner.milestone198.IVA_IMAGE_SHA256
                        if image == runner.IVA_IMAGE else "b" * 64)

            with patch.object(runner, "DATA", root), \
                 patch.object(runner, "RESULTS", results), \
                 patch.object(runner, "image_id", side_effect=fake_image_id), \
                 patch.object(runner, "sha", return_value=runner.milestone198.MANIFEST_SHA256), \
                 patch.object(runner, "verify_identical_micall_base"), \
                 patch.object(runner, "verify_execution_image_binding"), \
                 patch.object(runner, "load_micall_projects", return_value=({}, "catalog")), \
                 patch("reference_panel.build_reference_panel", return_value=[("r", "ACGT")] * 33), \
                 patch("reference_panel.panel_sha256", return_value=runner.milestone198.PANEL_SHA256), \
                 patch.object(runner, "iva_cache_status", return_value={"missing_or_invalid": [], "verified": ["all"]}), \
                 patch.object(runner, "evaluate_sample", side_effect=fake_sample), \
                 patch.object(sys, "argv", ["bench", "--mode", "ivanka",
                                           "--qualify-198", "--all-projects",
                                           "--jobs", "2"]):
                self.assertEqual(runner.main(), 1)

            events = [json.loads(line) for line in
                      (results / "results.jsonl").read_text().splitlines()]
            self.assertEqual({e["sample"] for e in events}, {"S0", "S1"})
            self.assertEqual(len(calls), 2)
            summary = json.loads(next(results.glob("summary-*.json")).read_text())
            self.assertTrue(summary["stopped_early_after_irreversible_failure"])
            self.assertFalse(summary["milestone198_pass"])
            self.assertIn("completed_result_count_not_198",
                          summary["milestone198_errors"])

if __name__ == "__main__":
    unittest.main()
