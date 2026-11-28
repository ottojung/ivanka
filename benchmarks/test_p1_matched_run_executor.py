"""Tests for the operator-ready matched-run executor."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from typing import Any

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
    "fingerprint": [5, 7], "leaf_value": "200000 100000",
    "leaf_only": True, "effective_source": "/libpod-test.scope",
    "chain": [{"path": "/libpod-test.scope", "raw": "200000 100000",
               "value": "200000 100000", "status": "ok"}],
    "chain_normalized": [["/libpod-test.scope", "200000 100000"]],
    "leaf_status": "ok", "scope": "host_scope_proven",
    "coverage": {"expected": 1, "read": 1, "missing": [],
                 "unreadable": [], "complete": True},
    "sample_identity": {"cid": "a" * 64, "pid": 4242,
                        "fingerprint": [5, 7],
                        "cgroup": "0::/libpod-test.scope",
                        "chain_normalized": [["/libpod-test.scope",
                                              "200000 100000"]]},
}
DIAGNOSTIC_OK = {"matched": True, "reasons": [],
                "host_scope_proven": True,
                "observed_value": "200000 100000"}

# The exact shape emitted by fail_closed_guard.natural_exit.attest. Only this
# guard-owned proof may make a zombie/terminal gap a proven natural exit.
TERMINAL_PROOF = {
    "cid": "a" * 64, "returncode": 0, "method": "exact_cid_inspect",
    "absence_proof": {"observed_absent": True, "inspected_absent_twice": True},
    "kernel_enforcement": False,
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
        "quota_diagnostic": DIAGNOSTIC_OK,
        "quota_drift": [],
        "host_scope_proven": True,
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
            absent = ex.kernel_cpu_max("0::/missing.scope\n", root)
            self.assertIsNone(absent["value"])
            self.assertEqual(absent["leaf_status"], "unavailable")
            self.assertFalse(absent["coverage"]["complete"])

    def test_observed_quota_uses_guard_bind_and_ancestor_walk(self) -> None:
        cid = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scope = root / ("libpod-" + cid + ".scope")
            scope.mkdir()
            (scope / "cpu.max").write_text("200000 100000\n")
            bound = {"cid": cid, "pid": 9, "fingerprint": [5, 7]}
            table = {
                7: {"cgroup": "0::/init.scope", "starttime": 5, "pid_ns": 7},
                9: {"cgroup": "0::/libpod-" + cid + ".scope",
                    "starttime": 5, "pid_ns": 7},
            }
            observed = ex.observe_bound_cpu_quota(table, bound, root)
            self.assertEqual(observed["pid"], 9)
            self.assertEqual(observed["cid"], cid)
            self.assertEqual(observed["fingerprint"], [5, 7])
            self.assertTrue(observed["leaf_only"])

            # A truncated-prefix collision on another PID must never bind.
            table[11] = {"cgroup": "0::/libpod-" + cid[:12] + ".scope",
                         "starttime": 5, "pid_ns": 7}
            self.assertEqual(ex.observe_bound_cpu_quota(table, bound, root)["pid"], 9)

            # Tighter ancestor makes the leaf value insufficient as proof.
            (root / "cpu.max").write_text("100000 100000\n")
            tighter = ex.observe_bound_cpu_quota(table, bound, root)
            self.assertEqual(tighter["value"], "100000 100000")
            self.assertEqual(tighter["leaf_value"], "200000 100000")
            self.assertFalse(tighter["leaf_only"])
            self.assertEqual(tighter["effective_source"], str(root))

            # Continuous observation reflects a mid-arm change instead of caching.
            (root / "cpu.max").unlink()
            (scope / "cpu.max").write_text("150000 100000\n")
            self.assertEqual(ex.observe_bound_cpu_quota(table, bound, root)["value"],
                             "150000 100000")

    def test_bound_identity_changes_fail_closed(self) -> None:
        cid = "b" * 64
        bound = {"cid": cid, "pid": 12, "fingerprint": [5, 7]}
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scope = root / ("libpod-" + cid + ".scope")
            scope.mkdir()
            (scope / "cpu.max").write_text("200000 100000\n")
            live = {12: {"cgroup": "0::/libpod-" + cid + ".scope",
                         "starttime": 5, "pid_ns": 7}}
            self.assertIsNotNone(ex.observe_bound_cpu_quota(live, bound, root))
            changed = {12: {**live[12], "starttime": 999}}
            self.assertIsNone(ex.observe_bound_cpu_quota(changed, bound, root))
            unreadable = {12: {**live[12], "cgroup": None}}
            self.assertIsNone(ex.observe_bound_cpu_quota(unreadable, bound, root))
            malformed = {12: live[12]}
            self.assertIsNone(ex.observe_bound_cpu_quota(malformed,
                              {**bound, "cid": "deadbeef"}, root))

    def test_observed_cpu_quota_mismatch_is_diagnostic_not_dropped(self) -> None:
        good = dict(OBSERVED_QUOTA)
        self.assertTrue(ex.quota_diagnostic(
            good, host_scope_proven=True)["matched"])
        self.assertFalse(ex.quota_diagnostic({**good, "value": "150000 100000"},
            host_scope_proven=True)["matched"])
        self.assertFalse(ex.quota_diagnostic({**good, "origin": "podman_hostconfig"},
            host_scope_proven=True)["matched"])
        self.assertFalse(ex.quota_diagnostic(good)["matched"])
        bad_coverage = {**good}
        bad_coverage["coverage"] = {**good["coverage"], "complete": False}
        self.assertFalse(ex.quota_diagnostic(
            bad_coverage, host_scope_proven=True)["matched"])
        drift = ex.compare_quota_samples(good, {
            **good,
            "sample_identity": {**good["sample_identity"],
                                "cgroup": "0::/other.scope",
                                "chain_normalized": [["/other.scope",
                                                      "200000 100000"]]}})
        self.assertIn("bound cgroup changed", drift)

    def test_missing_intermediate_and_root_only_are_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            mid = root / "slice-a"
            leaf = mid / "libpod-test.scope"
            leaf.mkdir(parents=True)
            (root / "cpu.max").write_text("200000 100000\n")
            (leaf / "cpu.max").write_text("200000 100000\n")
            # Missing intermediate controller is recorded, not silently skipped.
            (mid / "cgroup.controllers").write_text("cpuset memory\n")
            observed = ex.kernel_cpu_max("0::/slice-a/libpod-test.scope\n", root)
            self.assertEqual(observed["value"], "200000 100000")
            self.assertIn(str(mid), observed["coverage"]["missing"])
            self.assertIsNone(observed["effective_source"])
            self.assertFalse(ex.quota_diagnostic(
                observed, host_scope_proven=True)["matched"])

            # Root-only reading cannot be presented as the leaf.
            (leaf / "cpu.max").unlink()
            root_only = ex.kernel_cpu_max("0::/slice-a/libpod-test.scope\n", root)
            self.assertEqual(root_only["leaf_status"], "unavailable")
            self.assertEqual(root_only["value"], "200000 100000")
            self.assertIsNone(root_only["leaf_value"])
            self.assertIsNone(root_only["effective_source"])

    def test_natural_exit_gap_does_not_poison_earlier_samples(self) -> None:
        previous = dict(OBSERVED_QUOTA)
        bound = {"cid": "a" * 64, "pid": 4242, "fingerprint": [5, 7]}
        zombie = {4242: {"state": "Z", "starttime": 5, "pid_ns": 7}}
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound, terminal_proof=TERMINAL_PROOF), "terminal")
        self.assertEqual(ex.sampling_gap_kind(
            previous, {}, bound, terminal_proof=TERMINAL_PROOF), "drift")
        self.assertIsNone(ex.sampling_gap_kind(
            None, zombie, bound, terminal_proof=TERMINAL_PROOF))

    def test_zombie_terminal_requires_full_bound_fingerprint(self) -> None:
        previous = dict(OBSERVED_QUOTA)
        bound = {"cid": "a" * 64, "pid": 4242, "fingerprint": [5, 7]}
        matching = {4242: {"state": "Z", "starttime": 5, "pid_ns": 7}}
        changed_starttime = {4242: {"state": "Z", "starttime": 999, "pid_ns": 7}}
        changed_namespace = {4242: {"state": "Z", "starttime": 5, "pid_ns": 999}}
        no_fingerprint = {4242: {"state": "Z"}}
        self.assertEqual(ex.sampling_gap_kind(
            previous, matching, bound, terminal_proof=TERMINAL_PROOF), "terminal")
        for record in (changed_starttime, changed_namespace, no_fingerprint):
            self.assertEqual(ex.sampling_gap_kind(
                previous, record, bound, terminal_proof=TERMINAL_PROOF), "drift")

    def test_natural_exit_needs_guard_owned_terminal_proof(self) -> None:
        previous = dict(OBSERVED_QUOTA)
        bound = {"cid": "a" * 64, "pid": 4242, "fingerprint": [5, 7]}
        zombie = {4242: {"state": "Z", "starttime": 5, "pid_ns": 7}}
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound, terminal_proof=TERMINAL_PROOF), "terminal")
        # No proof, a caller assertion, or a malformed/foreign proof is drift.
        self.assertEqual(ex.sampling_gap_kind(previous, zombie, bound), "drift")
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound, terminal_proof=True), "drift")
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound,
            terminal_proof={**TERMINAL_PROOF, "cid": "b" * 64}), "drift")
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound,
            terminal_proof={**TERMINAL_PROOF, "method": "caller_asserted"}), "drift")
        self.assertEqual(ex.sampling_gap_kind(
            previous, zombie, bound, terminal_proof={
                **TERMINAL_PROOF,
                "absence_proof": {"observed_absent": True,
                                  "inspected_absent_twice": False}}), "drift")

    def test_guard_terminal_proof_is_guard_owned(self) -> None:
        self.assertEqual(
            ex.guard_terminal_proof(TERMINAL_PROOF, cid="a" * 64), TERMINAL_PROOF)
        self.assertIsNone(ex.guard_terminal_proof(TERMINAL_PROOF, cid="b" * 64))
        self.assertIsNone(ex.guard_terminal_proof(None))
        self.assertIsNone(ex.guard_terminal_proof({"method": "exact_cid_inspect"}))

    def test_caller_assertion_cannot_set_host_scope_proven(self) -> None:
        self.assertFalse(ex.host_scope_proven_from_proof(True))
        self.assertFalse(ex.host_scope_proven_from_proof("host_scope_proven"))
        self.assertFalse(ex.host_scope_proven_from_proof(
            {"asserted": True, "scope": "host_scope_proven"}))
        # Only a structured, separately attested proof is recognized.
        self.assertTrue(ex.host_scope_proven_from_proof({
            "schema": ex.HOST_SCOPE_PROOF_SCHEMA,
            "cgroup_root": "/sys/fs/cgroup",
            "attested_by": "operator-review",
        }))
        # A caller assertion fed through the diagnostic stays diagnostic-only.
        diagnostic = ex.quota_diagnostic(
            OBSERVED_QUOTA,
            host_scope_proven=ex.host_scope_proven_from_proof(True))
        self.assertFalse(diagnostic["host_scope_proven"])
        self.assertFalse(diagnostic["matched"])
        self.assertIn("visible hierarchy only; host scope not proven",
                      diagnostic["reasons"])

    def test_terminal_sample_gap_claim_requires_guard_proof(self) -> None:
        guarded = {
            "terminal_sample_gap": True,
            "observed_cpu_quota": dict(OBSERVED_QUOTA),
            "guard_outcome": {"result": {"natural_exit": TERMINAL_PROOF}},
        }
        self.assertTrue(ex.guard_terminal_sample_gap(guarded))
        unauthenticated = (
            {**guarded, "guard_outcome": {"result": {}}},
            {**guarded, "guard_outcome": {"result": {"natural_exit": True}}},
            {**guarded, "guard_outcome": {
                "result": {"natural_exit": {**TERMINAL_PROOF, "cid": "b" * 64}}}},
            {**guarded, "observed_cpu_quota": {**OBSERVED_QUOTA, "cid": "b" * 64}},
            {**guarded, "observed_cpu_quota": None},
            {**guarded, "terminal_sample_gap": False},
        )
        for raw in unauthenticated:
            self.assertFalse(ex.guard_terminal_sample_gap(raw))

    def test_execute_plan_does_not_inherit_unauthenticated_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)

            def spoofing(step, argv, arm_dir, *, deadline=None):
                raw = fake_arm_runner(step, argv, arm_dir, deadline=deadline)
                raw["host_scope_proven"] = True
                raw["terminal_sample_gap"] = True
                return raw

            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=spoofing,
                allow_unready=True, host_evidence=calm_host_evidence)
            self.assertEqual(len(receipt["records"]), 8)
            for record in receipt["records"]:
                self.assertFalse(record["host_scope_proven"])
                self.assertFalse(record["quota_diagnostic"]["host_scope_proven"])
                self.assertFalse(record["cpu_quota_diagnostic"]["host_scope_proven"])
                self.assertFalse(record["terminal_sample_gap"])
                self.assertIn("unauthenticated terminal_sample_gap claim refused",
                              record["cpu_quota_drift"])

    def test_execute_plan_accepts_only_structured_authenticated_claims(self) -> None:
        host_scope_proof = {
            "schema": ex.HOST_SCOPE_PROOF_SCHEMA,
            "cgroup_root": "/sys/fs/cgroup",
            "attested_by": "operator-review",
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)

            def guarded(step, argv, arm_dir, *, deadline=None):
                raw = fake_arm_runner(step, argv, arm_dir, deadline=deadline)
                raw["host_scope_proof"] = host_scope_proof
                raw["terminal_sample_gap"] = True
                raw["guard_outcome"] = {"result": {"natural_exit": TERMINAL_PROOF}}
                return raw

            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=guarded,
                allow_unready=True, host_evidence=calm_host_evidence)
            for record in receipt["records"]:
                self.assertTrue(record["host_scope_proven"])
                self.assertTrue(record["quota_diagnostic"]["host_scope_proven"])
                self.assertTrue(record["terminal_sample_gap"])
                self.assertNotIn("unauthenticated terminal_sample_gap claim refused",
                                 record["cpu_quota_drift"])

        # An explicit caller assertion still cannot masquerade as proof.
        for proof in (True, "host_scope_proven", {"asserted": True}):
            with tempfile.TemporaryDirectory() as tmp:
                out = pathlib.Path(tmp) / "out"
                emitted = plan.build_plan(RECEIPT, out)
                receipt = ex.execute_plan(
                    emitted, output_root=out, arm_runner=fake_arm_runner,
                    allow_unready=True, host_evidence=calm_host_evidence,
                    host_scope_proof=proof)
                self.assertFalse(receipt["records"][0]["host_scope_proven"])

    def test_production_gap_is_terminal_only_with_guard_proof(self) -> None:
        cid = "a" * 64
        bound = {"cid": cid, "pid": 4242, "fingerprint": [5, 7]}
        live = {4242: {"cgroup": "0::/libpod-" + cid + ".scope",
                       "starttime": 5, "pid_ns": 7}}
        zombie = {4242: {"state": "Z", "starttime": 5, "pid_ns": 7}}
        captured: dict[str, Any] = {}

        def local_runner_factory(**kwargs):
            captured["snapshot"] = kwargs["snapshot"]
            captured["bind"] = kwargs["bind_container"]

            def run(step, argv, arm_dir, *, deadline=None):
                captured["bind"](cid, {})
                captured["tables"] = [live, zombie]
                captured["snapshot"]()  # records a live quota observation
                captured["snapshot"]()  # records the terminal gap candidate
                return {"status": "completed", "guard_outcome": {
                    "result": {"natural_exit": captured.get("proof")}}}
            return run

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scope = root / ("libpod-" + cid + ".scope")
            scope.mkdir()
            (scope / "cpu.max").write_text("200000 100000\n")
            att = root / "att.json"
            att.write_text("{}")

            with mock.patch.object(ex.plan, "readiness",
                                   return_value={"ready": True, "reasons": []}), \
                    mock.patch.object(ex, "guarded_podman_arm_runner",
                                      side_effect=local_runner_factory), \
                    mock.patch("fail_closed_guard.binding.bind_container",
                               return_value=bound), \
                    mock.patch("fail_closed_guard.proc.snapshot",
                               side_effect=lambda: captured["tables"].pop(0)):
                runner = ex.build_production_arm_runner(
                    owner="o", lease_root=root / "leases",
                    stop_path=root / "STOP", disk_path=root,
                    lock_path=root / "lock", watchdog_path=root / "wd",
                    watchdog_graphroot=root, attestation=att,
                    cgroup_root=root)
                step = {"case": "c", "arm": "frozen"}
                # Guard-owned proof plus matching fingerprint: natural exit.
                captured["proof"] = TERMINAL_PROOF
                result = runner(step, [], root / "arm1")
                self.assertTrue(result["terminal_sample_gap"])
                self.assertEqual(result["quota_drift"], [])
                self.assertFalse(result["host_scope_proven"])
                # The same gap without a guard proof is drift, not terminal.
                captured["proof"] = None
                result = runner(step, [], root / "arm2")
                self.assertFalse(result["terminal_sample_gap"])
                self.assertIn("bound init disappeared or became unreadable",
                              result["quota_drift"])

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
                requested_cpu_max="200000 100000", observed_cpu_quota=OBSERVED_QUOTA,
            quota_diagnostic=DIAGNOSTIC_OK))
        decision = plan.comparability_check(records, cases=plan.ALL_CASES)
        self.assertTrue(decision["comparable"])


    def test_mismatch_is_preserved_as_diagnostic_receipt(self) -> None:
        def mismatched(step, argv, arm_dir, *, deadline=None):
            result = fake_arm_runner(step, argv, arm_dir, deadline=deadline)
            result["observed_cpu_quota"] = {
                **OBSERVED_QUOTA, "value": "150000 100000"}
            result["observed_container_cpu_max"] = "150000 100000"
            result["quota_diagnostic"] = ex.quota_diagnostic(
                result["observed_cpu_quota"], host_scope_proven=True)
            return result

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out"
            emitted = plan.build_plan(RECEIPT, out)
            receipt = ex.execute_plan(
                emitted, output_root=out, arm_runner=mismatched,
                allow_unready=True, host_evidence=calm_host_evidence)
            self.assertTrue((out / "receipt.json").is_file())
            self.assertTrue(receipt["comparability"]["abort"])
            for record in receipt["records"]:
                self.assertFalse(record["cpu_quota_complete"])
                self.assertEqual(record["cpu_quota"]["observed_container_cpu_max"],
                                 "150000 100000")
                self.assertFalse(record["cpu_quota_diagnostic"]["matched"])
                self.assertIn("quota value differs from request",
                              record["cpu_quota_diagnostic"]["reasons"])


if __name__ == "__main__":
    unittest.main()
