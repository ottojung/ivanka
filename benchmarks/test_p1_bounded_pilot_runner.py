"""Deterministic injected tests for the P1 bounded prospective pilot runner.

No live podman, no live image build, no frozen receipt mutation, no /tmp
evidence paths.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fail_closed_guard.errors import GuardExceeded

from expanded import p1_bounded_pilot_runner as runner
from expanded.p1_full464_controller import (
    MEMORY_BYTES, WALL_CAP_SECONDS,
)


CID = "a" * 64


def make_case_dir(root, case_id="clonal-s000"):
    case = Path(root) / case_id
    (case / "reads").mkdir(parents=True)
    (case / "hidden-truth").mkdir(parents=True)
    (case / "reads" / "R1.fastq.gz").write_bytes(b"R1")
    (case / "reads" / "R2.fastq.gz").write_bytes(b"R2")
    (case / "hidden-truth" / "haplotypes.fasta").write_text(">t\nACGT\n")
    hashes = {
        "reads/R1.fastq.gz": runner.sha256(case / "reads/R1.fastq.gz"),
        "reads/R2.fastq.gz": runner.sha256(case / "reads/R2.fastq.gz"),
        "hidden-truth/haplotypes.fasta": runner.sha256(
            case / "hidden-truth/haplotypes.fasta"),
    }
    manifest = {
        "schema": "ivanka.synthetic_case_manifest.v2",
        "id": case_id,
        "family": "clonal",
        "hidden_truth_file": "hidden-truth/haplotypes.fasta",
        "score_model_revision": 2,
        "sha256": hashes,
    }
    (case / "manifest.json").write_text(json.dumps(manifest))
    return case, hashes, manifest


def fake_bind(cid, env, snapshot=None):
    return {"cid": cid, "pid": 100, "stable": True, "starttime": 5,
            "pid_ns": 7, "fingerprint": [5, 7], "cmdline_sha": "x"}


def fake_stop(cid):
    return {"cid": cid, "container_removed": True,
            "fresh_absence_check": True,
            "method": "exact_cid_inspect_absent",
            "absence_proof": {"observed_absent": True}}


class RunnerSourceTests(unittest.TestCase):
    def test_no_name_based_kill_or_old_rss_tree(self):
        src = Path(runner.__file__).read_text()
        self.assertNotIn("rss_tree(", src)
        self.assertNotIn('podman", "kill"', src)
        self.assertNotIn("subprocess.run([\"podman\", \"kill\"", src)

    def test_defaults_are_workspace_not_tmp(self):
        self.assertTrue(runner.DEFAULT_EVIDENCE_ROOT.startswith("/workspace"))
        self.assertTrue(runner.DEFAULT_STOP.startswith("/workspace"))
        self.assertTrue(runner.DEFAULT_LEASE_ROOT.startswith("/workspace"))
        self.assertNotIn("/tmp", runner.DEFAULT_EVIDENCE_ROOT)
        self.assertNotIn("/tmp", runner.DEFAULT_STOP)
        self.assertNotIn("/tmp", runner.DEFAULT_LEASE_ROOT)

    def test_explicit_default_case_list_no_full464(self):
        self.assertEqual(len(runner.DEFAULT_CASES), 3)
        self.assertEqual(len(set(runner.DEFAULT_CASES)), 3)
        self.assertLess(len(runner.DEFAULT_CASES), 464)

    def test_absolute_limits_pinned(self):
        self.assertEqual(runner.WALL_CAP_SECONDS, 2400)
        self.assertEqual(runner.MEMORY_BYTES, 4_000_000_000)
        self.assertEqual(runner.PODMAN_TIMEOUT_SECONDS, 2398)


class FakePopen:
    def __init__(self, cmd, env=None, stdout=None, stderr=None):
        self.cmd = list(cmd)
        self.returncode = 0
        self._polls = 0
        self.pid = 4242
        # simulate podman writing cidfile
        if "--cidfile" in self.cmd:
            idx = self.cmd.index("--cidfile") + 1
            Path(self.cmd[idx]).write_text(CID + "\n")
        if stdout is not None:
            try:
                stdout.write(b"ok\n")
            except Exception:
                pass

    def poll(self):
        self._polls += 1
        if self._polls <= 1:
            return None
        self.returncode = 0
        return 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def fake_snapshot():
    return {
        100: {"pid": 100, "ppid": 1, "starttime": 5, "pid_ns": 7,
              "cmdline_sha": "x", "rss": 1024 * 1024,
              "cgroup": "0::/user.slice/container.scope",
              "structural_unavailable": False},
    }


class RunCaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.case_dir, self.hashes, self.manifest = make_case_dir(
            self.data, "clonal-s000")
        self.out = self.root / "out"
        self.out.mkdir()
        self.timer = self.root / "timer.py"
        self.timer.write_text("print('timer')\n")
        self.stop_path = self.root / "STOP"
        self.lease_root = self.root / "leases"
        self.lock_path = self.root / "pilot.lock"
        self.env = {}

    def _run_case(self, **overrides):
        destination = self.out / "clonal-s000"
        # prepare timing.json that scoring expects
        timing = {
            "timing_origin": "micall_in_container_monotonic_v1",
            "exit_code": 0,
            "seconds": 12.5,
        }
        def fake_spawn_side_effect(cmd, env=None, stdout=None, stderr=None):
            proc = FakePopen(cmd, env=env, stdout=stdout, stderr=stderr)
            # write timing after "container starts" - destination exists
            (destination / "timing.json").write_text(json.dumps(timing))
            return proc

        kwargs = dict(
            case_id="clonal-s000", case_dir=self.case_dir,
            destination=destination, image="d" * 64, commit="c" * 40,
            timer=self.timer, env=self.env, owner="test-owner",
            lock_path=str(self.lock_path), stop_path=str(self.stop_path),
            lease_root=str(self.lease_root), disk_path=str(self.root),
            case_hashes=self.hashes,
            watchdog_ready=lambda: {"ready": True, "identity_bound": True,
                                    "pid_ns": 7, "starttime": 5},
            watchdog_snapshot=fake_snapshot,
            disk_usage=lambda p: os.statvfs(p) if False else type(
                "U", (), {"free": 10 ** 12})(),
            bind_container=fake_bind, stop_cid_fn=fake_stop,
            snapshot=fake_snapshot, clock=lambda: 0.0,
            sleep=lambda _: None, audit=lambda e: e,
            heartbeat_root=str(self.lease_root),
        )
        kwargs.update(overrides)

        metrics = {
            "score": 9900.0, "score_origin": "micall_final_max_abundant_truths_balanced_v2",
            "dominant_exact": True,
            "source": {"per_truth": {"truth_0": {"score": 950, "length": 1000,
                                                  "fraction": 0.95}}}
        }
        with (
            mock.patch.object(runner.subprocess, "Popen", side_effect=fake_spawn_side_effect),
            mock.patch.object(runner, "evaluate_final_alignment", return_value=metrics),
            mock.patch.object(runner, "public_diagnostics", return_value={"ok": True}),
            mock.patch.object(runner, "score_outputs", return_value={"outputs": {}}),
            mock.patch.object(runner, "seal_terminal_evidence",
                              return_value=(destination / "terminal_evidence.json", "h")),
            mock.patch.object(runner, "terminal_retire", return_value={"retired": True}),
        ):
            # ensure evidence file exists for seal
            (destination.parent).mkdir(parents=True, exist_ok=True)
            return runner.run_case(**kwargs)

    def test_success_writes_receipt_with_fresh_absence(self):
        row = self._run_case()
        self.assertEqual(row["result"]["status"], "success")
        self.assertEqual(row["case_id"], "clonal-s000")
        receipt = json.loads(
            (self.out / "clonal-s000" / "receipt.json").read_text())
        self.assertEqual(receipt["schema"],
                         "ivanka.p1.bounded-pilot-case-receipt.v1")
        teardown = receipt["guard"]["teardown"]
        self.assertTrue(teardown["fresh_absence_check"])
        self.assertTrue(teardown["container_removed"])
        self.assertEqual(receipt["guard"]["kernel_enforcement"], False)
        self.assertIn("rss_sample_scope", receipt["guard"])

    def test_watchdog_readiness_required(self):
        row = self._run_case(watchdog_ready=lambda: (_ for _ in ()).throw(
            GuardExceeded("watchdog_unavailable")))
        self.assertEqual(row["result"]["status"], "failed")
        self.assertEqual(row["result"]["guard_error"], "watchdog_unavailable")
        # no container spawn when pre-spawn gate fails
        self.assertIsNone(row["result"]["exit_code"])

    def test_stop_owner_mismatch_fails_closed(self):
        self.stop_path.write_text("someone-else\n")
        row = self._run_case()
        self.assertEqual(row["result"]["status"], "failed")
        self.assertEqual(row["result"]["guard_error"], "stop_owner_unauthorized")


class RunnerBehaviorTests(RunCaseIntegrationTests):
    def test_absolute_limits_passed_to_guard(self):
        captured = {}
        real = runner.p1_harness.run_prospective

        def spy(*args, **kwargs):
            captured.update(kwargs)
            captured["args"] = args
            return real(*args, **kwargs)

        with mock.patch.object(runner.p1_harness, "run_prospective", side_effect=spy):
            self._run_case()
        self.assertEqual(captured["limit"], MEMORY_BYTES)
        self.assertEqual(captured["wall_seconds"], WALL_CAP_SECONDS)
        self.assertEqual(captured["disk_reserve_bytes"], runner.RESERVE_GIB * 1024 ** 3)

    def test_heartbeat_callback_passed_to_guard(self):
        captured = {}
        real = runner.p1_harness.run_prospective

        def spy(*args, **kwargs):
            captured["heartbeat"] = kwargs.get("heartbeat")
            return real(*args, **kwargs)

        with mock.patch.object(runner.p1_harness, "run_prospective", side_effect=spy):
            self._run_case()
        self.assertIsNotNone(captured["heartbeat"])
        self.assertTrue(callable(captured["heartbeat"]))

    def test_no_truth_at_assembly_time(self):
        events = []
        real_eval = mock.Mock(return_value={
            "score": 9900.0, "score_origin": "micall_final_max_abundant_truths_balanced_v2",
            "dominant_exact": True,
            "source": {"per_truth": {"truth_0": {"score": 950, "length": 1000,
                                                  "fraction": 0.95}}}
        })

        def record_eval(*args, **kwargs):
            events.append("score")
            return real_eval(*args, **kwargs)

        def fake_spawn(cmd, env=None, stdout=None, stderr=None):
            events.append("spawn")
            proc = FakePopen(cmd, env=env, stdout=stdout, stderr=stderr)
            (self.out / "clonal-s000" / "timing.json").write_text(json.dumps({
                "timing_origin": "micall_in_container_monotonic_v1",
                "exit_code": 0, "seconds": 12.5}))
            return proc

        destination = self.out / "clonal-s000"
        with mock.patch.object(runner.subprocess, "Popen", side_effect=fake_spawn), \
             mock.patch.object(runner, "evaluate_final_alignment", side_effect=record_eval), \
             mock.patch.object(runner, "public_diagnostics", return_value={}), \
             mock.patch.object(runner, "score_outputs", return_value={"outputs": {}}), \
             mock.patch.object(runner, "seal_terminal_evidence",
                               return_value=(destination / "terminal_evidence.json", "h")), \
             mock.patch.object(runner, "terminal_retire", return_value={}):
            row = runner.run_case(
                case_id="clonal-s000", case_dir=self.case_dir,
                destination=destination, image="d" * 64, commit="c" * 40,
                timer=self.timer, env=self.env, owner="test-owner",
                lock_path=str(self.lock_path), stop_path=str(self.stop_path),
                lease_root=str(self.lease_root), disk_path=str(self.root),
                case_hashes=self.hashes,
                watchdog_ready=lambda: {"ready": True, "identity_bound": True,
                                        "pid_ns": 7, "starttime": 5},
                watchdog_snapshot=fake_snapshot,
                disk_usage=lambda p: type("U", (), {"free": 10 ** 12})(),
                bind_container=fake_bind, stop_cid_fn=fake_stop,
                snapshot=fake_snapshot, clock=lambda: 0.0,
                sleep=lambda _: None, audit=lambda e: e,
                heartbeat_root=str(self.lease_root))
        self.assertEqual(row["result"]["status"], "success")
        self.assertIn("spawn", events)
        self.assertIn("score", events)
        self.assertLess(events.index("spawn"), events.index("score"))

    def test_uses_shared_guard_run_prospective(self):
        with mock.patch.object(runner.p1_harness, "run_prospective",
                               wraps=runner.p1_harness.run_prospective) as spy:
            self._run_case()
        self.assertEqual(spy.call_count, 1)


class BuildCommandTests(unittest.TestCase):
    def test_command_has_cidfile_limits_and_no_rm(self):
        cmd = runner.build_command("/case", "/out", "d" * 64, "/timer.py",
                                   "name", "/cidfile")
        joined = " ".join(cmd)
        self.assertIn("--cidfile /cidfile", joined)
        self.assertIn("--memory=4000000000", joined)
        self.assertIn("--timeout 2398", joined)
        self.assertNotIn("--rm", cmd)
        runner.assert_reference_blind(cmd)

    def test_command_rejects_truth_mount(self):
        cmd = runner.build_command("/case", "/out", "d" * 64, "/timer.py",
                                   "name", "/cidfile")
        bad = cmd + ["-v", "/hidden-truth:/x:ro"]
        with self.assertRaises(ValueError):
            runner.assert_reference_blind(bad)


class RunOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.case_dir, self.hashes, self.manifest = make_case_dir(
            self.data, "clonal-s000")
        self.timer = self.root / "timer.py"
        self.timer.write_text("x\n")
        self.out = self.root / "evidence"

    def test_run_manifest_and_summary_mark_nogo_and_no_full464(self):
        args = mock.Mock()
        args.data = self.data
        args.frozen_results = self.root / "frozen.jsonl"
        args.timer = self.timer
        args.out = self.out
        args.storage_conf = None
        args.cases = "clonal-s000"
        args.image = "d" * 64
        args.commit = "c" * 40
        args.lock = str(self.root / "pilot.lock")
        args.stop = str(self.root / "STOP")
        args.lease_root = str(self.root / "leases")
        args.disk_path = self.root
        args.watchdog_path = self.root / "watchdog.json"
        args.watchdog_graphroot = self.root / "graphroot"
        args.owner = "test-owner"
        args.reserve_gib = runner.RESERVE_GIB
        args.admission_gib = runner.ADMISSION_GIB

        fake_row = {
            "case_id": "clonal-s000",
            "result": {"status": "success", "error": ""},
        }
        with mock.patch.object(runner, "verify_pins"), \
             mock.patch.object(runner, "verify_image", return_value={"k": "v"}), \
             mock.patch.object(runner, "load_case_hashes",
                               return_value=({ "clonal-s000": self.hashes }, {}, "f" * 64)), \
             mock.patch.object(runner, "verify_case_hashes", return_value=self.hashes), \
             mock.patch.object(runner, "run_case", return_value=fake_row):
            summary = runner.run(args, watchdog_ready=lambda: {
                "ready": True, "identity_bound": True, "pid_ns": 7,
                "starttime": 5})

        self.assertFalse(summary["qualified"])
        self.assertIn("NO-GO", summary["guard_status"])
        self.assertTrue(summary["all_succeeded"])
        manifest = json.loads((self.out / "run_manifest.json").read_text())
        self.assertFalse(manifest["qualified"])
        self.assertTrue(manifest["no_full464_rerun"])
        self.assertFalse(manifest["truth_used_at_assembly_time"])
        self.assertEqual(manifest["explicit_case_list"], ["clonal-s000"])

    def test_main_requires_watchdog_args(self):
        with self.assertRaises(SystemExit):
            runner.main(["--out", str(self.out)])
