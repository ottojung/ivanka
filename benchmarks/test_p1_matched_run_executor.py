"""Tests for the operator-ready matched-run executor."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import p1_matched_run_executor as ex
import p1_ultradeep_matched_runtime as plan

RECEIPT = (
    pathlib.Path(__file__).parent.parent
    / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json"
)


CALM_HOST = {"loadavg": [1.0, 1.0, 1.0], "cpu_max": "200000 100000",
             "effective_cpus": 2.0, "cpuset_effective": "0-1",
             "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
             "memory_current": 1000}


def calm_host_evidence():
    return dict(CALM_HOST)


OBSERVED_QUOTA = {
    "value": "200000 100000", "origin": plan.KERNEL_QUOTA_ORIGINS[0],
    "raw": "200000 100000", "cgroup_path": "/libpod-test.scope",
    "source": "/sys/fs/cgroup/libpod-test.scope/cpu.max",
    "pid": 4242, "cgroup": "0::/libpod-test.scope", "cid": "a" * 64,
}


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
        "requested_container_cpu_max": "200000 100000",
        "observed_cpu_quota": OBSERVED_QUOTA,
        "observed_container_cpu_max": "200000 100000",
        "host_before": CALM_HOST,
        "host_after": {**CALM_HOST, "loadavg": [1.1, 1.0, 1.0], "cpu_stat": {"nr_periods": 110, "nr_throttled": 0}},
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
                allow_unready=True,
                host_evidence=calm_host_evidence)
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
                allow_unready=True,
                host_evidence=calm_host_evidence)
            self.assertEqual(receipt["schedule_len"], 12)
            self.assertTrue(receipt["comparability"]["comparable"])
            self.assertEqual(receipt["comparability"]["reasons"], [])

    def test_output_root_must_match_emitted_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            emitted = plan.build_plan(RECEIPT, tmp / "plan-root")
            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=tmp / "other-root",
                                arm_runner=fake_arm_runner, allow_unready=True,
                                host_evidence=calm_host_evidence)

    def test_tampered_late_step_refuses_before_any_arm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            emitted["schedule"][3]["argv"].append("--unexpected")
            calls = []

            def counting(*args, **kwargs):
                calls.append(args)
                return {}

            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out, arm_runner=counting,
                                allow_unready=True, host_evidence=calm_host_evidence)
            self.assertEqual(calls, [])

    def test_normalize_timing_rejects_bad_origin_and_over_timeout(self) -> None:
        with self.assertRaises(ex.Refusal):
            ex._normalize_timing({"seconds": 1.0, "timing_origin": "bad", "exit_code": 0})
        with self.assertRaises(ex.Refusal):
            ex._normalize_timing({"seconds": 2401.0,
                                  "timing_origin": ex.TIMING_ORIGIN, "exit_code": 0})

    def test_preflight_contention_refuses_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            calls = []

            def counting(*args, **kwargs):
                calls.append(args)
                return {}

            hot = {"loadavg": [100.0, 1.0, 1.0], "cpu_max": "200000 100000",
                   "effective_cpus": 2.0, "cpuset_effective": "0-1",
                   "cpu_stat": {"nr_periods": 100, "nr_throttled": 0},
                   "memory_current": 1}
            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out, arm_runner=counting,
                                allow_unready=True, host_evidence=lambda: dict(hot))
            self.assertEqual(calls, [])

    def test_log_sha_mismatch_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out, cases=plan.CASES[:1])

            def bad_sha(step, argv, arm_dir, **kw):
                arm_dir.mkdir(parents=True, exist_ok=True)
                timing = {"seconds": 100.0, "timing_origin": ex.TIMING_ORIGIN, "exit_code": 0}
                (arm_dir / "timing.json").write_text(json.dumps(timing))
                (arm_dir / "podman.log").write_text("actual")
                return {"status": "completed", "timing": timing,
                        "sampled_rss_bytes": 1, "container_cpu_max": "200000 100000",
                        "log_sha256": "0" * 64,
                        "host_before": CALM_HOST, "host_after": CALM_HOST}

            with self.assertRaises(ex.Refusal):
                ex.execute_plan(emitted, output_root=out, arm_runner=bad_sha,
                                allow_unready=True, host_evidence=calm_host_evidence)

    def test_production_runner_requires_ready_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            att = pathlib.Path(tmp) / "att.json"
            att.write_text("{}")
            with self.assertRaises(ex.Refusal):
                ex.build_production_arm_runner(
                    owner="o", lease_root=pathlib.Path(tmp)/"leases",
                    stop_path=pathlib.Path(tmp)/"STOP",
                    disk_path=pathlib.Path(tmp),
                    lock_path=pathlib.Path(tmp)/"lock",
                    watchdog_path=pathlib.Path(tmp)/"wd",
                    watchdog_graphroot=pathlib.Path(tmp),
                    attestation=att)

    def test_cli_production_missing_args_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            script = pathlib.Path(__file__).parent / "p1_matched_run_executor.py"
            completed = subprocess.run(
                [sys.executable, str(script), "--receipt", str(RECEIPT),
                 "--output-root", str(out), "--cases", "ultradeep-s006",
                 "--arm-runner", "production"],
                capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution"], "refused")
            self.assertIn("missing required args", payload["reason"])

    def test_kernel_cpu_max_reads_real_cgroup_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scope = root / "libpod-abcdef.scope"
            scope.mkdir()
            (scope / "cpu.max").write_text("200000 100000\n")
            observed = ex.kernel_cpu_max("0::/libpod-abcdef.scope\n", root)
            self.assertEqual(observed["value"], "200000 100000")
            self.assertEqual(observed["origin"], ex.CPU_MAX_ORIGIN_V2)
            self.assertEqual(observed["raw"], "200000 100000")
            self.assertEqual(ex.normalize_cpu_max("max 100000"), "max 100000")
            self.assertIsNone(ex.normalize_cpu_max("bogus 100000"))
            self.assertIsNone(ex.kernel_cpu_max("0::/missing.scope\n", root))

    def test_observed_quota_binds_exact_cid_and_rejects_foreign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scope = root / "libpod-abcdef123456.scope"
            scope.mkdir()
            (scope / "cpu.max").write_text("200000 100000\n")
            table = {
                7: {"cgroup": "0::/init.scope"},
                9: {"cgroup": "0::/libpod-abcdef123456.scope"},
            }
            observed = ex.find_observed_cpu_quota(table, "abcdef1234567890", root)
            self.assertEqual(observed["pid"], 9)
            self.assertEqual(observed["cid"], "abcdef1234567890")
            self.assertIsNone(ex.find_observed_cpu_quota(table, "ffffffffffffffff", root))

    def test_missing_observed_quota_fails_comparability(self) -> None:
        def no_quota(step, argv, arm_dir, *, deadline=None):
            result = fake_arm_runner(step, argv, arm_dir, deadline=deadline)
            result.pop("observed_cpu_quota")
            result.pop("observed_container_cpu_max")
            return result

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=no_quota,
                allow_unready=True, host_evidence=calm_host_evidence)
            self.assertTrue(receipt["comparability"]["abort"])
            self.assertTrue(any("kernel CPU quota" in r
                                for r in receipt["comparability"]["reasons"]))
            for rec in receipt["records"]:
                self.assertFalse(rec["cpu_quota_complete"])
                self.assertIsNone(rec["cpu_quota"]["observed_cpu_max_origin"])
                self.assertEqual(rec["cpu_quota"]["requested_container_cpu_max"],
                                 "200000 100000")
            evidence = json.loads((out / plan.CASES[0] / "frozen" / "host-evidence.json").read_text())
            self.assertIsNone(evidence["cpu_quota"]["observed_container_cpu_max"])

    def test_operator_environment_is_real_and_store_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conf = pathlib.Path(tmp) / "storage.conf"
            conf.write_text('[storage]\ndriver = "overlay"\ngraphroot = "/tmp/graph"\nrunroot = "/tmp/run"\n')
            env = ex.operator_environment(
                conf, base_env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                "HOME": "/home/lubko", "CONTAINERS_CONF": "/foreign"})
            self.assertIn("PATH", env)
            self.assertIn("HOME", env)
            self.assertNotIn("CONTAINERS_CONF", env)
            self.assertEqual(env["CONTAINERS_STORAGE_CONF"], str(conf))
            with self.assertRaises(plan.Refusal):
                ex.operator_environment(conf, base_env={"HOME": "/home/lubko"})

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
                sampled_rss_bytes=1_000_000_000, container_cpu_max="200000 100000",
                requested_cpu_max="200000 100000", observed_cpu_quota=OBSERVED_QUOTA))
        decision = plan.comparability_check(records, cases=plan.ALL_CASES)
        self.assertTrue(decision["comparable"])


if __name__ == "__main__":
    unittest.main()
