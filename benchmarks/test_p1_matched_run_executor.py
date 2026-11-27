"""Tests for the operator-ready matched-run executor."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import p1_matched_run_executor as ex
import p1_ultradeep_matched_runtime as plan

RECEIPT = (
    pathlib.Path(__file__).parent.parent
    / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json"
)


def fake_arm_runner(step, argv, arm_dir, *, deadline=None):
    arm_dir.mkdir(parents=True, exist_ok=True)
    arm = step["arm"]
    seconds = 100.0 + (0.1 if arm == "candidate" else 0.0)
    timing = {"seconds": seconds, "timing_origin": "micall_in_container_monotonic_v1", "exit_code": 0}
    (arm_dir / "timing.json").write_text(json.dumps(timing))
    log = "2026-11-27 00:00:00,000 INFO sample_setup start\n2026-11-27 00:00:01,000 INFO sample_setup done\n"
    (arm_dir / "podman.log").write_text(log)
    return {
        "status": "completed",
        "timing": timing,
        "exit_code": 0,
        "log_path": str(arm_dir / "podman.log"),
        "sampled_rss_bytes": 1_500_000_000,
        "container_cpu_max": "200000 100000",
        "host_before": {"loadavg": [1.0, 1.0, 1.0], "cpu_max": "200000 100000",
                         "effective_cpus": 2.0, "cpuset_effective": "0-1",
                         "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
                         "memory_current": 1000},
        "host_after": {"loadavg": [1.1, 1.0, 1.0], "cpu_max": "200000 100000",
                        "effective_cpus": 2.0, "cpuset_effective": "0-1",
                        "cpu_stat": {"nr_periods": 110, "nr_throttled": 0},
                        "memory_current": 1000},
    }


class ExecutorTest(unittest.TestCase):
    def test_default_runner_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out)

    def test_unready_plan_refuses_without_allow_unready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out, arm_runner=fake_arm_runner)

    def test_mocked_execution_writes_fresh_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=fake_arm_runner,
                allow_unready=True)
            self.assertEqual(receipt["schema"], ex.RECEIPT_SCHEMA)
            self.assertEqual(receipt["execution"], "executed")
            self.assertEqual(receipt["schedule_len"], 8)
            self.assertEqual(len(receipt["records"]), 8)
            self.assertTrue((out / "receipt.json").is_file())
            for rec in receipt["records"]:
                self.assertIn("log_sha256", rec)
                self.assertTrue(rec["rss_evidence_complete"])
                self.assertTrue(rec["cpu_quota_complete"])
                # stage_timing is present when log markers are parseable; absent otherwise
                if "stage_timing" in rec:
                    self.assertIsInstance(rec["stage_timing"], dict)

    def test_controls_schedule_has_12_arms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out, cases=plan.ALL_CASES)
            self.assertEqual(len(emitted["schedule"]), 12)
            self.assertEqual(emitted["cases"], list(plan.ALL_CASES))
            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=fake_arm_runner,
                allow_unready=True)
            self.assertEqual(receipt["schedule_len"], 12)
            self.assertTrue(receipt["comparability"]["comparable"])
            self.assertEqual(receipt["comparability"]["reasons"], [])

    def test_comparability_check_accepts_case_count(self) -> None:
        records = []
        for step in plan.alternating_schedule(plan.ALL_CASES):
            records.append(plan.arm_evidence_record(
                step,
                {"loadavg": [1, 1, 1], "cpu_max": "200000 100000", "effective_cpus": 2.0,
                 "cpuset_effective": "0-1", "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
                 "memory_current": 1},
                {"loadavg": [1, 1, 1], "cpu_max": "200000 100000", "effective_cpus": 2.0,
                 "cpuset_effective": "0-1", "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
                 "memory_current": 1},
                {"seconds": 100.0, "exit_code": 0},
                sampled_rss_bytes=1_000_000_000, container_cpu_max="200000 100000"))
        decision = plan.comparability_check(records, cases=plan.ALL_CASES)
        self.assertTrue(decision["comparable"])


if __name__ == "__main__":
    unittest.main()
