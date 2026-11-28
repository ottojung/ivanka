"""Hermetic tests for the operator readiness CLI.

No private manifest, guard root, Podman store, MiCall container, truth asset or
benchmark cohort is touched. The only real guard code exercised is the merged
read-only preflight/watchdog/disk logic; all host-specific observations are
injected through a fake probe with deterministic values.
"""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from assembler_bench import remap_guarded_exec as gexec
from assembler_bench import remap_pilot_cli as cli
from assembler_bench import remap_pilot_controller as ctl
from assembler_bench import remap_runner as runner
from fail_closed_guard import heartbeat

STAMP = "20261127T120000Z"
TOKEN = "deadbeef"
R1_NAME = "R001_L001_R1_001.fastq.gz"
R2_NAME = "R001_L001_R2_001.fastq.gz"
R1_BYTES = b"hermetic-read-one\n"
R2_BYTES = b"hermetic-read-two\n"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class _Probe(cli.LiveProbes):
    """Deterministic observations; real merged logic still runs downstream."""

    def __init__(self, *, free=None, lock=True, image=True, stop=None,
                 watchdog_ready=True, watchdog_reason="watchdog_unbound",
                 env_clean=True, cid_fresh=True):
        self.free = runner.RESERVE_BYTES + 1024 if free is None else free
        self.lock = lock
        self.image_ok = image
        self.stop_state = stop if stop is not None else {
            "armed": True, "owner": "operator-test"}
        self.watchdog_ready = watchdog_ready
        self.watchdog_reason = watchdog_reason
        self.env_clean = env_clean
        self.cid_fresh = cid_fresh

    def disk_free(self, path, *, reserve_bytes=None):
        return self.free

    def lock_free(self, path):
        return self.lock

    def image(self, image_id, image_digest, storage_conf):
        return ({"present": True, "digest": image_digest} if self.image_ok
                else {"present": False, "reason": "image_missing"})

    def stop(self, path):
        return dict(self.stop_state)

    def watchdog(self, path, graphroot, snapshot=None):
        if not self.watchdog_ready:
            return {"ready": False, "reason": self.watchdog_reason}
        return super().watchdog(path, graphroot, snapshot=snapshot)

    def environment(self, storage_conf):
        return {"clean": self.env_clean, "ambient": [],
                "foreign_storage_conf": False}

    def cid_absent(self, cidfile):
        return self.cid_fresh and super().cid_absent(cidfile)

    def git_head(self):
        return "hermetic-head"


class RemapPilotCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="remap-cli-"))
        self.reads = self.root / "reads"
        self.reads.mkdir()
        (self.reads / R1_NAME).write_bytes(R1_BYTES)
        (self.reads / R2_NAME).write_bytes(R2_BYTES)
        self.r1, self.r2 = _sha(R1_BYTES), _sha(R2_BYTES)
        self.manifest_path = self.root / "readback.json"
        cases = []
        for index in range(198):
            alias = f"PX-R{index + 1:03d}"
            cases.append({
                "alias": alias, "cohort": "physical",
                "reads": {"R1": {"sha256": self.r1 if alias == "PX-R001" else "a" * 64,
                                 "source_verified": True, "bytes": len(R1_BYTES)},
                          "R2": {"sha256": self.r2 if alias == "PX-R001" else "b" * 64,
                                 "source_verified": True, "bytes": len(R2_BYTES)}},
            })
        for index in range(464):
            cases.append({
                "alias": f"PX-H{index + 1:03d}", "cohort": "synthetic",
                "reads": {"R1": {"sha256": "c" * 64, "source_verified": True, "bytes": 1},
                          "R2": {"sha256": "d" * 64, "source_verified": True, "bytes": 1}},
            })
        self.document = {
            "schema": "ivanka.remap.read-pair-preflight.v1",
            "counts": {"physical": 198, "synthetic": 464},
            "errors": [], "truth_opened": False,
            "physical_manifest_sha256": "e" * 64,
            "synthetic_cohort_sha256": "f" * 64,
            "cases": cases,
        }
        raw = json.dumps(self.document, sort_keys=True, separators=(",", ":")).encode()
        self.manifest_path.write_bytes(raw)
        self.manifest_sha = _sha(raw)
        self.graphroot = str(self.root / "store")
        self.runroot = str(self.root / "run")
        self.storage_conf = self.root / "storage.conf"
        self.storage_conf.write_text(
            '[storage]\ndriver = "overlay"\n'
            f'graphroot = "{self.graphroot}"\nrunroot = "{self.runroot}"\n')
        self.guard = self.root / "guard"
        self.guard.mkdir()
        self.lock = self.guard / ".global-worker.lock"
        self.lock.write_text("")
        self.stop_path = self.guard / ".remap-pilot.STOP"
        self.stop_path.write_text("operator-test\n")
        self.watchdog_path = self.guard / ".watchdog-alive.json"
        identity = heartbeat.identity(os.getpid())
        self.snapshot = {os.getpid(): {
            "starttime": identity["fingerprint"][0],
            "pid_ns": identity["fingerprint"][1]}}
        self.watchdog_path.write_text(json.dumps({
            "schema": "ivanka.watchdog-alive.v1", "at_utc": time.time(),
            "graphroot": self.graphroot, "pid": os.getpid(),
            "fingerprint": identity["fingerprint"],
            "cmdline_sha": identity["cmdline_sha"]}, sort_keys=True))
        self.attempt = self.root / "attempt"
        self.attempt.mkdir()
        self.cidfile = self.attempt / "cid"
        self.config = replace(
            cli.ReadinessConfig(),
            manifest_path=self.manifest_path, manifest_sha256=self.manifest_sha,
            guard_root=self.guard, lock_path=self.lock, stop_path=self.stop_path,
            watchdog_path=self.watchdog_path, storage_conf=self.storage_conf)
        self.probe = _Probe()
        self.panel = self.root / "panel.json"
        self.panel.write_bytes(b'{"hermetic":"posthoc-panel"}')
        self.panel_sha = _sha(self.panel.read_bytes())
        panel_patch = patch.object(runner, "PANEL_SHA256", self.panel_sha)
        panel_patch.start()
        self.addCleanup(panel_patch.stop)
        self.authorization = self.root / "authorization.json"
        self.checker_file = self.root / "watchdog-checker.json"
        self.identity = heartbeat.identity(os.getpid())
        self._write_authorization()
        self._write_checker()

    def _write_authorization(self, **overrides):
        record = {
            "schema": cli.AUTHORIZATION_SCHEMA,
            "id": "auth-hermetic-1",
            "issue": cli.ISSUE_ID,
            "operator": "operator-test",
            "alias": "R001",
            "run_id": f"remap-real-{STAMP.lower()}-{TOKEN}",
            "token_sha256": _sha(TOKEN.encode()),
            "scope": cli.AUTHORIZATION_SCOPE,
            "expires_at_utc": time.time() + 3600,
            "watchdog_graphroot": self.graphroot,
        }
        record.update(overrides)
        self.authorization.write_text(json.dumps(record, sort_keys=True))

    def _write_checker(self, **overrides):
        record = {
            "schema": cli.WATCHDOG_CHECKER_SCHEMA,
            "ready": True,
            "identity_bound": True,
            "pid_ns": self.identity["fingerprint"][1],
            "starttime": self.identity["fingerprint"][0],
            "at_utc": time.time(),
        }
        record.update(overrides)
        self.checker_file.write_text(json.dumps(record, sort_keys=True))

    def fake_execute(self, calls):
        def run(pilot, **kwargs):
            calls.append((pilot, kwargs))
            return {
                "schema": "ivanka.remap-diagnostic.receipt.v1",
                "run_id": kwargs["plan"]["run_id"],
                "alias": pilot.alias,
                "status": "measured",
                "receipt_sha256": "a" * 64,
                "qualification_claim": "NONE",
            }
        return run

    def report(self, **kwargs):
        options = dict(alias="R001", reads_dir=self.reads,
                       attempt_dir=self.attempt, cidfile=self.cidfile,
                       stamp=STAMP, token=TOKEN, config=self.config,
                       probes=self.probe, snapshot=lambda: self.snapshot)
        options.update(kwargs)
        return cli.build_readiness_report(**options)

    def cli_args(self):
        return ["readiness", "--alias", "R001", "--reads-dir", str(self.reads),
                "--attempt-dir", str(self.attempt), "--cidfile", str(self.cidfile),
                "--stamp", STAMP, "--token", TOKEN]

    def exec_args(self):
        args = self.cli_args()
        args[0] = "execute"
        return args + [
            "--operator", "operator-test",
            "--authorization-file", str(self.authorization),
            "--watchdog-checker-file", str(self.checker_file),
            "--panel-path", str(self.panel),
        ]

    def run_execute(self, calls, *, argv=None, clock=None):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main(argv or self.exec_args(), config=self.config,
                          probes=self.probe, execute=self.fake_execute(calls),
                          snapshot=lambda: self.snapshot, clock=clock)
        return rc, json.loads(stdout.getvalue())

    def test_positive_admitted_without_execution(self):
        with patch.object(ctl, "execute_case",
                          side_effect=AssertionError("must not execute")) as execute:
            report = self.report()
        self.assertTrue(report["admitted"], report["blockers"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["inputs"]["read_sha256"]["R1"], self.r1)
        self.assertEqual(report["inputs"]["read_sha256"]["R2"], self.r2)
        self.assertEqual(report["inputs"]["canonical_manifest_sha256"],
                         runner.input_manifest([runner.Case(
                             alias="R001", cohort="real", r1_sha256=self.r1,
                             r2_sha256=self.r2, reads_dir=str(self.reads),
                             attempt_dir=str(self.attempt), timer="",
                             cidfile=str(self.cidfile), storage_root=self.graphroot,
                             runroot=self.runroot, name="n")]))
        self.assertNotIn("--denovo", report["plan"]["argv"])
        self.assertIn("--all_projects", report["plan"]["argv"])
        self.assertTrue(report["preflight"]["admitted"])
        for key in ("executed", "would_execute", "execution_authorized"):
            self.assertIs(report[key], False)
        self.assertEqual(report["qualification_claim"], "NONE")
        execute.assert_not_called()

    def test_cli_exit_zero_and_json_report(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main(self.cli_args(), config=self.config, probes=self.probe)
        self.assertEqual(rc, cli.EXIT_ADMITTED)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["admitted"])
        self.assertFalse(payload["executed"])

    def test_cli_exit_two_on_below_reserve(self):
        self.probe.free = runner.RESERVE_BYTES - 1
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main(self.cli_args(), config=self.config, probes=self.probe)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        payload = json.loads(stdout.getvalue())
        self.assertIn("reserve", payload["blockers"])
        self.assertFalse(payload["admitted"])

    def test_manifest_sha_pin_is_not_bypassable(self):
        bad = replace(self.config, manifest_sha256="0" * 64)
        report = self.report(config=bad)
        self.assertFalse(report["admitted"])
        self.assertTrue(any(b.startswith("manifest_unattested")
                            for b in report["blockers"]))

    def test_tampered_read_hash_fails_closed(self):
        (self.reads / R1_NAME).write_bytes(b"tampered\n")
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertTrue(any(b.startswith("input_or_plan_rejected")
                            for b in report["blockers"]))

    def test_alias_not_in_manifest_fails_closed(self):
        report = self.report(alias="R999")
        self.assertFalse(report["admitted"])
        self.assertIn("alias_not_attested", report["blockers"])

    def test_lock_held_fails_closed(self):
        self.probe.lock = False
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("exclusive_slot", report["blockers"])

    def test_stop_not_armed_fails_closed(self):
        self.probe.stop_state = {"armed": False, "owner": None}
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("stop_not_armed", report["blockers"])

    def test_watchdog_unbound_fails_closed(self):
        self.watchdog_path.write_text(json.dumps({
            "schema": "ivanka.watchdog-alive.v1", "at_utc": time.time(),
            "graphroot": "/foreign/store", "pid": os.getpid(),
            "fingerprint": heartbeat.identity(os.getpid())["fingerprint"],
            "cmdline_sha": heartbeat.identity(os.getpid())["cmdline_sha"]},
            sort_keys=True))
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertTrue(any(b.startswith("watchdog_not_ready")
                            for b in report["blockers"]))

    def test_preexisting_cidfile_fails_closed(self):
        self.cidfile.write_text("pre-existing\n")
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("cidfile_not_fresh", report["blockers"])

    def test_image_missing_fails_closed(self):
        self.probe.image_ok = False
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("image_missing", report["blockers"])

    def test_ambient_selector_fails_closed(self):
        self.probe.env_clean = False
        report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("ambient_selector_or_foreign_storage_conf",
                      report["blockers"])

    def test_truth_token_in_argv_fails_closed(self):
        original = runner.plan_case

        def leaking(*args, **kwargs):
            plan = original(*args, **kwargs)
            plan["argv"] = list(plan["argv"]) + ["/truth/haplotypes.fasta"]
            return plan

        with patch.object(runner, "plan_case", side_effect=leaking):
            report = self.report()
        self.assertFalse(report["admitted"])
        self.assertIn("truth_mounted", report["blockers"])

    def test_internal_error_returns_exit_one(self):
        with patch.object(gexec, "load_original_input_manifest",
                          side_effect=RuntimeError("burst pipe")):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = cli.main(self.cli_args(), config=self.config,
                              probes=self.probe)
        self.assertEqual(rc, cli.EXIT_ERROR)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["blockers"], ["internal_error:RuntimeError"])
        self.assertFalse(payload["executed"])


    def test_execute_positive_wiring_with_fake_controller(self):
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_ADMITTED)
        self.assertTrue(report["executed"])
        self.assertTrue(report["execution_authorized"])
        self.assertEqual(report["receipt"]["qualification_claim"], "NONE")
        self.assertEqual(report["authorization"]["scope"], cli.AUTHORIZATION_SCOPE)
        self.assertEqual(len(calls), 1)
        pilot, kwargs = calls[0]
        self.assertEqual(pilot.alias, "R001")
        self.assertEqual(pilot.panel_sha256, self.panel_sha)
        self.assertEqual(kwargs["operator_owner"], "operator-test")
        self.assertEqual(kwargs["stop_path"], self.config.stop_path)
        self.assertEqual(kwargs["guard_root"], self.config.guard_root)
        self.assertIsNone(kwargs.get("runner"))
        self.assertIsNone(kwargs.get("scorer"))
        self.assertIsNone(kwargs.get("spawn"))
        self.assertTrue(kwargs["preflight_result"]["admitted"])
        self.assertTrue(callable(kwargs["watchdog_ready"]))
        self.assertEqual(kwargs["watchdog_ready"]()["pid_ns"],
                         self.identity["fingerprint"][1])
        self.assertNotIn("--denovo", kwargs["plan"]["argv"])

    def test_execute_without_authorization_never_calls_controller(self):
        self.authorization.unlink()
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertFalse(report["executed"])
        self.assertTrue(any(b.startswith("authorization_rejected")
                            for b in report["blockers"]))
        self.assertEqual(calls, [])

    def test_execute_rejects_wrong_scope_token_operator_and_expiry(self):
        for overrides in (
            {"scope": "anything_else"},
            {"token_sha256": "0" * 64},
            {"operator": "foreign-owner"},
            {"alias": "R002"},
            {"expires_at_utc": time.time() - 10},
        ):
            with self.subTest(overrides=overrides):
                self._write_authorization(**overrides)
                calls = []
                rc, report = self.run_execute(calls)
                self.assertEqual(rc, cli.EXIT_BLOCKED)
                self.assertFalse(report["executed"])
                self.assertEqual(calls, [])

    def test_execute_rejects_nonfinite_authorization_timestamps(self):
        for overrides, clock in (
            ({"expires_at_utc": float("nan")}, None),
            ({"expires_at_utc": float("inf")}, None),
            ({"expires_at_utc": float("-inf")}, None),
            ({}, lambda: float("nan")),
            ({}, lambda: float("inf")),
        ):
            with self.subTest(overrides=overrides, has_clock=clock is not None):
                self._write_authorization(**overrides)
                calls = []
                rc, report = self.run_execute(calls, clock=clock)
                self.assertEqual(rc, cli.EXIT_BLOCKED)
                self.assertFalse(report["executed"])
                self.assertTrue(any(b.startswith("authorization_rejected")
                                    for b in report["blockers"]))
                self.assertEqual(calls, [])

    def test_execute_rejects_below_reserve_and_held_slot(self):
        for mutate in (lambda: setattr(self.probe, "free",
                                       runner.RESERVE_BYTES - 1),
                       lambda: setattr(self.probe, "lock", False)):
            with self.subTest():
                mutate()
                calls = []
                rc, report = self.run_execute(calls)
                self.assertEqual(rc, cli.EXIT_BLOCKED)
                self.assertFalse(report["executed"])
                self.assertEqual(calls, [])

    def test_execute_rejects_stop_owner_mismatch(self):
        self.probe.stop_state = {"armed": True, "owner": "someone-else"}
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertIn("stop_owner_mismatch", report["blockers"])
        self.assertEqual(calls, [])

    def test_execute_rejects_unbound_watchdog_checker(self):
        for overrides in ({"identity_bound": False},
                          {"pid_ns": 1, "starttime": 1},
                          {"at_utc": time.time() - 3600}):
            with self.subTest(overrides=overrides):
                self._write_checker(**overrides)
                calls = []
                rc, report = self.run_execute(calls)
                self.assertEqual(rc, cli.EXIT_BLOCKED)
                self.assertFalse(report["executed"])
                self.assertEqual(calls, [])

    def test_checker_is_fresh_once_then_uses_live_alive_each_sample(self):
        checker = cli._watchdog_checker(
            self.checker_file, config=self.config, graphroot=self.graphroot,
            snapshot=lambda: self.snapshot)
        first = checker()
        self.assertEqual((first["starttime"], first["pid_ns"]),
                         (self.identity["fingerprint"][0],
                          self.identity["fingerprint"][1]))
        # A stale or removed operator file must not age out an armed case;
        # the live watchdog record is verified independently every sample.
        self._write_checker(at_utc=time.time() - 3600)
        later = checker()
        self.assertTrue(later["ready"])
        self.assertGreaterEqual(later["at_utc"], first["at_utc"])
        original = self.watchdog_path.read_text()
        stale = json.loads(original)
        stale["at_utc"] = time.time() - 3600
        self.watchdog_path.write_text(json.dumps(stale, sort_keys=True))
        with self.assertRaises(ValueError):
            checker()
        self.watchdog_path.write_text(original)

    def test_checker_rejects_replacement_watchdog_identity(self):
        checker = cli._watchdog_checker(
            self.checker_file, config=self.config, graphroot=self.graphroot,
            snapshot=lambda: self.snapshot)
        self.assertTrue(checker()["ready"])
        original = self.watchdog_path.read_text()
        replacement_pid = self.identity["pid"] + 1 if "pid" in self.identity \
            else os.getpid() + 1
        fingerprint = [111, 222]
        self.snapshot[replacement_pid] = {
            "starttime": fingerprint[0], "pid_ns": fingerprint[1]}
        replacement = {
            "schema": "ivanka.watchdog-alive.v1",
            "at_utc": time.time(),
            "graphroot": self.graphroot,
            "pid": replacement_pid,
            "fingerprint": fingerprint,
            "cmdline_sha": self.identity["cmdline_sha"]}
        self.watchdog_path.write_text(json.dumps(replacement, sort_keys=True))
        with self.assertRaisesRegex(ValueError, "identity_drift"):
            checker()
        self.watchdog_path.write_text(original)

    def test_execute_rejects_stale_alive_and_future_checker(self):
        original = self.watchdog_path.read_text()
        alive = json.loads(original)
        alive["at_utc"] = time.time() - 3600
        self.watchdog_path.write_text(json.dumps(alive, sort_keys=True))
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertFalse(report["executed"])
        self.assertTrue(report["blockers"])
        self.assertEqual(calls, [])
        checker = cli._watchdog_checker(
            self.checker_file, config=self.config, graphroot=self.graphroot,
            snapshot=lambda: self.snapshot)
        with self.assertRaises(ValueError):
            checker()
        self.watchdog_path.write_text(original)
        self._write_checker(at_utc=time.time() + 3600)
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertFalse(report["executed"])
        self.assertEqual(calls, [])

    def test_execute_rejects_panel_drift_and_synthetic_alias(self):
        self.panel.write_bytes(b'{"hermetic":"tampered"}')
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertIn("panel_digest_drift", report["blockers"])
        self.assertEqual(calls, [])
        self.panel.write_bytes(b'{"hermetic":"posthoc-panel"}')
        args = self.exec_args()
        args[args.index("R001")] = "H001"
        rc, report = self.run_execute(calls, argv=args)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertFalse(report["executed"])
        self.assertTrue(report["blockers"])
        self.assertEqual(calls, [])

    def test_execute_rejects_preexisting_cid_and_truth_token(self):
        self.cidfile.write_text("pre-existing\n")
        calls = []
        rc, report = self.run_execute(calls)
        self.assertEqual(rc, cli.EXIT_BLOCKED)
        self.assertIn("cidfile_not_fresh", report["blockers"])
        self.assertEqual(calls, [])

    def test_execute_report_forwards_full_plan_to_real_controller_path(self):
        captured = {}
        manifest = gexec.load_original_input_manifest(
            self.manifest_path, expected_sha=self.manifest_sha)

        def fake_guarded(plan, original_manifest, **kwargs):
            captured["plan"] = plan
            captured["manifest"] = original_manifest
            captured["kwargs"] = kwargs
            return {
                "schema": gexec.EXECUTION_SCHEMA,
                "status": "failed",
                "failure_reason": "test_stop_before_spawn",
                "returncode": 1,
                "timed_out": False,
                "log_paths": {},
                "bound_cid": None,
                "unmount_verified": False,
                "guard_receipt": None,
                "samples": 0,
                "observation_ended": False,
                "wall_seconds": 0.1,
                "peak_rss_bytes": None,
            }

        with patch.object(gexec, "load_original_input_manifest",
                          return_value=manifest), \
             patch.object(gexec, "run_guarded_case", side_effect=fake_guarded):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = cli.main(self.exec_args(), config=self.config,
                              probes=self.probe, snapshot=lambda: self.snapshot)
            report = json.loads(stdout.getvalue())
        self.assertEqual(rc, cli.EXIT_ADMITTED)
        self.assertTrue(report["executed"])
        self.assertEqual(report["receipt"]["status"], "failed")
        self.assertIn("plan", captured)
        plan = captured["plan"]
        for key in ("schema", "inputs", "qualification_claim", "de_novo",
                    "cohort", "alias", "image", "source", "reference",
                    "guard", "argv", "run_id"):
            self.assertIn(key, plan)
        self.assertEqual(plan["schema"], runner.PLAN_SCHEMA)
        self.assertRegex(plan["inputs"]["canonical_manifest_sha256"],
                         r"^[0-9a-f]{64}$")
        self.assertEqual(report["receipt"]["qualification_claim"], "NONE")

    def test_real_run_guarded_case_pre_spawn_rejects_trimmed_plan(self):
        manifest = gexec.load_original_input_manifest(
            self.manifest_path, expected_sha=self.manifest_sha)
        full_report = self.report()
        full_plan = dict(full_report["plan"])
        # Old bug shape: only summary fields, missing inputs/schema/markers.
        trimmed = {k: full_plan[k] for k in (
            "run_id", "argv_sha256", "argv", "image", "source",
            "reference", "guard")}
        with self.assertRaises(ValueError):
            gexec.run_guarded_case(trimmed, manifest,
                                   output_dir=self.root / "out-trimmed",
                                   attempt_dir=self.root / "att-trimmed",
                                   owner="operator-test",
                                   stop_path=self.config.stop_path,
                                   watchdog_ready=lambda: True,
                                   guard_root=self.config.guard_root)
        # Full plan passes manifest binding and fails closed before any spawn
        # because owner is not armed for this real guard path.
        result = gexec.run_guarded_case(
            full_plan, manifest, output_dir=self.root / "out-full",
            attempt_dir=self.root / "att-full", owner=None,
            stop_path=self.config.stop_path, watchdog_ready=lambda: True,
            guard_root=self.config.guard_root)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "operator_slot_not_armed")
        self.assertEqual(result["original_input_binding"]["alias"], "R001")


class LiveProbeImageTests(unittest.TestCase):
    IMAGE_ID = runner.IMAGE_ID
    IMAGE_DIGEST = runner.IMAGE_DIGEST

    def setUp(self):
        self.probe = cli.LiveProbes()
        self.storage_conf = Path("/tmp/fake-storage.conf")

    def _run(self, stdout="", returncode=0):
        class R:
            pass
        r = R()
        r.stdout = stdout
        r.stderr = ""
        r.returncode = returncode
        return r

    def test_normalize_image_id_accepts_full_hex_and_sha256_prefix(self):
        full = self.IMAGE_ID
        self.assertEqual(self.probe._normalize_image_id(full), full)
        self.assertEqual(self.probe._normalize_image_id("sha256:" + full), full)
        self.assertIsNone(self.probe._normalize_image_id(full[:12]))
        self.assertIsNone(self.probe._normalize_image_id("sha256:" + full[:12]))
        self.assertIsNone(self.probe._normalize_image_id("not-a-digest"))

    def test_image_probe_uses_no_trunc_and_requires_exact_match(self):
        full_line = f"sha256:{self.IMAGE_ID} {self.IMAGE_DIGEST} localhost/micall:x\n"
        with patch.object(cli, "_storage_paths", return_value=("/g", "/r")):
            with patch.object(cli.subprocess, "run",
                              return_value=self._run(full_line)) as run:
                report = self.probe.image(self.IMAGE_ID, self.IMAGE_DIGEST,
                                          self.storage_conf)
        self.assertTrue(report["present"])
        self.assertEqual(report["image_id"], self.IMAGE_ID)
        cmd = run.call_args.args[0]
        self.assertIn("--no-trunc", cmd)
        self.assertIn("--digests", cmd)
        self.assertEqual(cmd[-2:], ["--format", "{{.ID}} {{.Digest}}"])

    def test_image_probe_rejects_truncated_id_even_with_matching_digest(self):
        truncated = f"{self.IMAGE_ID[:12]} {self.IMAGE_DIGEST} localhost/micall:x\n"
        with patch.object(cli, "_storage_paths", return_value=("/g", "/r")):
            with patch.object(cli.subprocess, "run",
                              return_value=self._run(truncated)):
                report = self.probe.image(self.IMAGE_ID, self.IMAGE_DIGEST,
                                          self.storage_conf)
        self.assertFalse(report["present"])
        self.assertEqual(report["reason"], "image_missing_or_digest_drift")

    def test_image_probe_rejects_wrong_digest(self):
        wrong_digest = "sha256:" + "0" * 64
        line = f"sha256:{self.IMAGE_ID} {wrong_digest} localhost/micall:x\n"
        with patch.object(cli, "_storage_paths", return_value=("/g", "/r")):
            with patch.object(cli.subprocess, "run",
                              return_value=self._run(line)):
                report = self.probe.image(self.IMAGE_ID, self.IMAGE_DIGEST,
                                          self.storage_conf)
        self.assertFalse(report["present"])
        self.assertEqual(report["reason"], "image_missing_or_digest_drift")

    def test_image_probe_rejects_prefix_id_match(self):
        other = "ab" + self.IMAGE_ID[2:]
        line = f"sha256:{other} {self.IMAGE_DIGEST} localhost/micall:x\n"
        with patch.object(cli, "_storage_paths", return_value=("/g", "/r")):
            with patch.object(cli.subprocess, "run",
                              return_value=self._run(line)):
                report = self.probe.image(self.IMAGE_ID, self.IMAGE_DIGEST,
                                          self.storage_conf)
        self.assertFalse(report["present"])
        self.assertEqual(report["reason"], "image_missing_or_digest_drift")

    def test_image_probe_rejects_invalid_expected_identity(self):
        with patch.object(cli, "_storage_paths", return_value=("/g", "/r")):
            report = self.probe.image(self.IMAGE_ID[:12], self.IMAGE_DIGEST,
                                      self.storage_conf)
        self.assertFalse(report["present"])
        self.assertEqual(report["reason"], "image_identity_invalid")


if __name__ == "__main__":
    unittest.main()
