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


if __name__ == "__main__":
    unittest.main()
