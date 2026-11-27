"""Hermetic real-path integration tests for the guarded matched-run executor.

The real shared guard (``fail_closed_guard.p1_harness.run_prospective``) runs
end to end against temporary journals, a synthetic /proc table and injected
spawn/bind/teardown seams. No container, image, shared STOP, PX slot, frozen
receipt, truth input or scientific gate is touched. These tests exercise the
executor-to-guard seam, not a mock of the guard.
"""
from __future__ import annotations

import itertools
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import p1_matched_run_executor as ex
import p1_ultradeep_matched_runtime as plan
from px_stage_interval_diagnostic import ORDER

CID = "c" * 64
PID = 100
OWNER = "hermetic-matched-run-owner"
RECEIPT = (
    pathlib.Path(__file__).parent.parent
    / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json"
)
MESSAGES = {
    "startup": "Starting on container with 32 CPUs.",
    "sample_setup": "Processing Sample X.",
    "merge_entropy": "Running merge_for_entropy on Sample X.",
    "fastq_g2p": "Running fastq_g2p on Sample X.",
    "native_assembly": "Running de novo assembly on Sample X.",
    "assembly_tail": "Assembled 3 contigs in 0:00:01.000",
    "remap": "Running remap on Sample X.",
    "sam2aln": "Running sam2aln on Sample X.",
    "aln2counts": "Running aln2counts on Sample X.",
    "coverage_plots": "Running coverage_plots on Sample X.",
    "cascade_report": "Running cascade_report on Sample X.",
    "sample_tail": "Finished sample Sample X.",
    "resistance": "Running resistance on Sample X.",
    "resistance_report": "Running resistance report on Sample X.",
    "run_tail": "Finished resistance of Sample X.",
    "done": "Done.",
}


def stage_log() -> str:
    base = datetime(2026, 1, 1)
    return "\n".join(
        (base + timedelta(seconds=index)).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        + "[INFO]micall.example(): " + MESSAGES[name]
        for index, name in enumerate(ORDER)
    )


def proc_record(pid: int = PID) -> dict:
    return {"pid": pid, "ppid": 1, "starttime": 5, "pid_ns": 7,
            "cmdline_sha": "hermetic", "rss": 1_000_000,
            "cgroup": "0::/", "structural_unavailable": False}


class GuardHarness:
    """Supplies every guard seam; every call is recorded for assertions."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.lease_root = root / "leases"
        self.lease_root.mkdir(parents=True, exist_ok=True)
        self.lock_path = root / "lock"
        self.stop_path = root / "STOP"
        self.stop_path.write_text(OWNER + "\n")
        self.table = {PID: proc_record()}
        self.calls = {"spawn": [], "bind": [], "stop": [], "watchdog": [], "disk": []}
        self.liveness = itertools.cycle([True, False])
        self.watchdog_ready = True
        self.free_bytes = 40_000_000_000
        self.rearm_stop = True

    def arm_stop(self) -> None:
        # The guard retires STOP after a successful arm with a valid proof;
        # the operator re-arms it for the next arm.
        if self.rearm_stop and not self.stop_path.exists():
            self.stop_path.write_text(OWNER + "\n")

    def host_evidence(self):
        # Deterministic aggregate snapshot; never read real host state.
        return {"loadavg": [1.0, 1.0, 1.0], "cpu_max": "200000 100000",
                "effective_cpus": 2.0, "cpuset_effective": "0-1",
                "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
                "memory_current": 1_000_000_000}

    def spawn(self, cidfile, env, *, argv, arm_dir):
        self.calls["spawn"].append(str(cidfile))
        pathlib.Path(cidfile).write_text(CID + "\n")
        arm_dir.mkdir(parents=True, exist_ok=True)
        is_candidate = any("--name" in token and token.endswith("candidate")
                           for token in argv)
        timing = {"seconds": 100.0 + (0.5 if is_candidate else 0.0),
                  "timing_origin": "micall_in_container_monotonic_v1",
                  "exit_code": 0}
        (arm_dir / "timing.json").write_text(json.dumps(timing))
        (arm_dir / "podman.log").write_text(stage_log())
        return None

    def bind(self, cid, env, snapshot=None):
        self.calls["bind"].append(cid)
        return {"cid": cid, "pid": PID, "stable": True, "starttime": 5,
                "pid_ns": 7, "fingerprint": [5, 7],
                "cmdline_sha": "hermetic", "cgroup": "0::/"}

    def stop(self, cid):
        self.calls["stop"].append(cid)
        return {"cid": cid, "container_removed": True,
                "fresh_absence_check": True, "kernel_enforcement": False}

    def checker(self):
        self.calls["watchdog"].append("ready")
        if not self.watchdog_ready:
            return {"ready": False}
        return {"ready": True, "identity_bound": True, "pid_ns": 7,
                "starttime": 5, "cid": CID}

    def usage(self, _path):
        self.calls["disk"].append("checked")
        return SimpleNamespace(free=self.free_bytes)

    def runner(self):
        inner = ex.guarded_podman_arm_runner(
            owner=OWNER, lease_root=self.lease_root, stop_path=self.stop_path,
            disk_path=self.root, container_cpu_max="200000 100000",
            lock_path=self.lock_path, watchdog_ready=self.checker,
            disk_usage=self.usage, host_evidence=self.host_evidence,
            spawn=self.spawn,
            running=lambda: next(self.liveness), measure=lambda: True,
            snapshot=lambda: self.table, clock=lambda: 0, sleep=lambda _: None,
            stop_cid=self.stop, bind_container=self.bind,
            attestation={"method": "hermetic", "version": "test"},
        )

        def rearming(step, argv, arm_dir, **kwargs):
            self.arm_stop()
            return inner(step, argv, arm_dir, **kwargs)

        return rearming


class GuardedExecutorIntegrationTest(unittest.TestCase):
    def _emit(self, out: pathlib.Path, cases: tuple[str, ...]):
        return plan.build_plan(RECEIPT, out, cases=cases)

    def test_real_guard_runs_arms_and_writes_fresh_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            harness = GuardHarness(pathlib.Path(tmp) / "harness")
            emitted = self._emit(out, ("ultradeep-s006", "ultradeep-s002"))
            with patch("fail_closed_guard.binding.inspect_pid", return_value=PID):
                receipt = ex.execute_plan(
                    emitted, output_root=out, arm_runner=harness.runner(),
                    allow_unready=True)
            self.assertEqual(receipt["execution"], "executed")
            self.assertEqual(receipt["schedule_len"], 4)
            self.assertEqual(len(harness.calls["spawn"]), 4)
            self.assertEqual(len(harness.calls["bind"]), 4)
            self.assertEqual(len(harness.calls["stop"]), 4)
            self.assertGreaterEqual(len(harness.calls["watchdog"]), 8)
            self.assertGreaterEqual(len(harness.calls["disk"]), 8)
            self.assertFalse(harness.stop_path.exists())
            for record in receipt["records"]:
                self.assertEqual(record["status"], "completed")
                self.assertTrue(record["rss_evidence_complete"])
                self.assertTrue(record["cpu_quota_complete"])
                self.assertTrue(record["contention"]["before"]["abort"] is False)
                self.assertIn("log_sha256", record)
                self.assertEqual(record["sampled_peak_rss_bytes"], 1_000_000)
                self.assertIn("guard_outcome", record)
                stage = record["stage_timing"]
                self.assertIn("stage_intervals_seconds", stage)
                self.assertEqual(stage["attribution"], ex.STAGE_ATTRIBUTION)
                arm_dir = out / record["case"] / record["arm"]
                self.assertTrue((arm_dir / "host-evidence.json").is_file())
                self.assertTrue((arm_dir / "argv.json").is_file())
            self.assertTrue((out / "receipt.json").is_file())
            summary = receipt["tail_vs_control"]
            self.assertEqual(summary["tails"]["cases"], ["ultradeep-s006"])
            self.assertEqual(summary["controls"]["cases"], ["ultradeep-s002"])
            self.assertFalse(summary["psi_computed"])
            self.assertFalse(summary["formal_qualification"])
            # Evidence is exclusively created: a second run cannot overwrite it.
            with patch("fail_closed_guard.binding.inspect_pid", return_value=PID):
                with self.assertRaises(plan.Refusal):
                    ex.execute_plan(emitted, output_root=out,
                                    arm_runner=harness.runner(),
                                    allow_unready=True)

    def test_closed_stop_refuses_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            harness = GuardHarness(pathlib.Path(tmp) / "harness")
            harness.stop_path.unlink()
            harness.rearm_stop = False
            emitted = self._emit(out, ("ultradeep-s006",))
            with patch("fail_closed_guard.binding.inspect_pid", return_value=PID):
                with self.assertRaises(ex.Refusal):
                    ex.execute_plan(emitted, output_root=out,
                                    arm_runner=harness.runner(),
                                    allow_unready=True)
            self.assertEqual(harness.calls["spawn"], [])

    def test_unready_watchdog_refuses_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            harness = GuardHarness(pathlib.Path(tmp) / "harness")
            harness.watchdog_ready = False
            emitted = self._emit(out, ("ultradeep-s006",))
            with patch("fail_closed_guard.binding.inspect_pid", return_value=PID):
                with self.assertRaises(ex.Refusal):
                    ex.execute_plan(emitted, output_root=out,
                                    arm_runner=harness.runner(),
                                    allow_unready=True)
            self.assertEqual(harness.calls["spawn"], [])

    def test_disk_shortfall_refuses_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            harness = GuardHarness(pathlib.Path(tmp) / "harness")
            harness.free_bytes = 1_000
            emitted = self._emit(out, ("ultradeep-s006",))
            with patch("fail_closed_guard.binding.inspect_pid", return_value=PID):
                with self.assertRaises(ex.Refusal):
                    ex.execute_plan(emitted, output_root=out,
                                    arm_runner=harness.runner(),
                                    allow_unready=True)
            self.assertEqual(harness.calls["spawn"], [])

    def test_tampered_argv_refused_before_any_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = self._emit(out, ("ultradeep-s006",))
            emitted["schedule"][0]["argv"].append("--privileged")
            calls = []

            def counting(*args, **kwargs):
                calls.append(args)
                return {}

            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out, arm_runner=counting,
                                allow_unready=True)
            self.assertEqual(calls, [])

    def test_summary_never_substitutes_missing_arm(self):
        records = [{"case": "ultradeep-s006", "arm": "frozen",
                    "status": "completed", "wall_seconds": 120.0}]
        summary = ex.summarize_tail_vs_control(records, plan.ALL_CASES)
        self.assertIn("ultradeep-s006", summary["incomplete_cases"])
        self.assertEqual(summary["tails"]["n"], 0)
        self.assertEqual(summary["tails"]["candidate_minus_frozen_seconds"], [])

    def test_cli_default_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            script = pathlib.Path(__file__).parent / "p1_matched_run_executor.py"
            completed = subprocess.run(
                [sys.executable, str(script), "--receipt", str(RECEIPT),
                 "--output-root", str(out), "--cases", "ultradeep-s006"],
                capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution"], "refused")
            self.assertFalse(payload["formal_qualification"])
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
