"""Deterministic injected tests for the PR527-rebased bounded P1 pilot controller.

No live podman, no image build/import, no real STOP/lease, no frozen receipt
mutation and no /tmp evidence paths. The shared guard's real heartbeat is
verified structurally; no caller heartbeat is injected.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fail_closed_guard.errors import GuardExceeded

from expanded import p1_bounded_pilot_runner as runner
from expanded.p1_full464_controller import MEMORY_BYTES, WALL_CAP_SECONDS

CID = "a" * 64
IMAGE = "d" * 64


def make_case_dir(root, case_id="equal_strains-s000"):
    case = Path(root) / case_id
    (case / "reads").mkdir(parents=True)
    (case / "hidden-truth").mkdir(parents=True)
    (case / "reads" / "R1.fastq.gz").write_bytes(b"R1")
    (case / "reads" / "R2.fastq.gz").write_bytes(b"R2")
    (case / "hidden-truth" / "haplotypes.fasta").write_text(">t\nACGT\n")
    hashes = {
        "reads/R1.fastq.gz": runner.sha256(case / "reads" / "R1.fastq.gz"),
        "reads/R2.fastq.gz": runner.sha256(case / "reads" / "R2.fastq.gz"),
        "hidden-truth/haplotypes.fasta": runner.sha256(
            case / "hidden-truth" / "haplotypes.fasta"),
    }
    (case / "manifest.json").write_text(json.dumps({
        "schema": "ivanka.synthetic_case_manifest.v2",
        "id": case_id, "family": "equal_strains",
        "hidden_truth_file": "hidden-truth/haplotypes.fasta",
        "score_model_revision": 2, "sha256": hashes,
    }, sort_keys=True))
    return case, hashes


def fake_bind(cid, env, snapshot=None):
    return {"cid": cid, "pid": 100, "stable": True, "starttime": 5,
            "pid_ns": 7, "fingerprint": [5, 7], "cmdline_sha": "x"}


def fake_stop(cid):
    return {"cid": cid, "container_removed": True,
            "fresh_absence_check": True,
            "method": "exact_cid_inspect_absent",
            "absence_proof": {"observed_absent": True}}


def fake_snapshot():
    return {
        100: {"pid": 100, "ppid": 1, "starttime": 5, "pid_ns": 7,
              "cmdline_sha": "x", "rss": 1024 * 1024,
              "cgroup": "0::/user.slice/container.scope",
              "structural_unavailable": False},
    }


class FakePopen:
    def __init__(self, cmd, env=None, stdout=None, stderr=None):
        self.cmd = list(cmd)
        self.returncode = 0
        self._polls = 0
        self.pid = 4242
        if "--cidfile" in self.cmd:
            Path(self.cmd[self.cmd.index("--cidfile") + 1]).write_text(CID + "\n")
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


class DesignAndSourceTests(unittest.TestCase):
    def test_case_design_four_residual_two_control_one_canary(self):
        cases, _ = runner.load_case_manifest()
        self.assertEqual(len(runner.explicit_cases(cases)), 6)
        self.assertEqual(len(cases["residual_cases"]), 4)
        self.assertEqual(len(cases["control_cases"]), 2)
        self.assertEqual(cases["physical_canary"]["case_id"],
                         "physical-canary-R042")
        self.assertTrue(cases["no_full464_rerun"])
        self.assertFalse(cases["truth_used_at_assembly_time"])

    def test_absolute_limits_and_disk_policy_pinned(self):
        self.assertEqual(runner.WALL_CAP_SECONDS, 2400)
        self.assertEqual(runner.MEMORY_BYTES, 4_000_000_000)
        self.assertEqual(runner.PODMAN_TIMEOUT_SECONDS, 2398)
        self.assertEqual(runner.PILOT_RESERVE_GIB, 32)
        self.assertEqual(runner.PILOT_RESERVATION_GIB, 1)
        self.assertEqual(runner.PILOT_REQUIRED_FREE_BYTES, 33 * 1024 ** 3)

    def test_shared_px_lock_lease_and_graphroot_defaults(self):
        self.assertEqual(runner.DEFAULT_LOCK,
                         runner.SHARED_PX_BOUNDARY["global_lock"])
        self.assertEqual(runner.DEFAULT_LEASE_ROOT,
                         runner.SHARED_PX_BOUNDARY["lease_root"])
        self.assertEqual(runner.DEFAULT_STORAGE_CONF,
                         runner.SHARED_PX_BOUNDARY["storage_conf"])
        self.assertEqual(runner.PINS_V2["storage_conf"],
                         runner.SHARED_PX_BOUNDARY["storage_conf_sha256"])
        self.assertEqual(runner.INTEGRATION_BASE,
                         "9f81086715cade9d383f4aec62e284873ab21ba0")
        # STOP stays owner-bound; exclusion primitives must be shared with PX.
        self.assertEqual(runner.DEFAULT_STOP,
                         str(runner.PILOT_ROOT / "p1-prospective.STOP"))
        self.assertNotEqual(runner.DEFAULT_LOCK,
                            str(runner.PILOT_ROOT / "pilot.lock"))
        self.assertNotIn(str(runner.PILOT_ROOT), runner.DEFAULT_LEASE_ROOT)

    def test_no_name_based_kill_or_old_rss_tree(self):
        src = Path(runner.__file__).read_text()
        self.assertNotIn("rss_tree(", src)
        self.assertNotIn('podman", "kill"', src)

    def test_guard_owns_real_heartbeat_and_runner_does_not_inject(self):
        guard_src = Path(runner.p1_harness.__file__).read_text()
        self.assertIn("heartbeat.Emitter", guard_src)
        self.assertIn("before_spawn", guard_src)
        self.assertIn("heartbeat=refresh_ready", guard_src)
        self.assertIn("emitter.refresh()", guard_src)
        runner_src = Path(runner.__file__).read_text()
        self.assertNotIn("heartbeat=", runner_src)

    def test_no_truth_mount_in_container_command(self):
        cmd = runner.build_command("/case", "/out", IMAGE, "/timer.py",
                                   "name", "/cidfile")
        runner.assert_reference_blind(cmd)
        self.assertIn("--cidfile /cidfile", " ".join(cmd))
        bad = cmd + ["-v", "/hidden-truth:/x:ro"]
        with self.assertRaises(ValueError):
            runner.assert_reference_blind(bad)


class PinAndBindingTests(unittest.TestCase):
    def test_case_and_image_manifests_match_pins(self):
        cases, sha = runner.load_case_manifest()
        self.assertEqual(sha, runner.PINS_V2["cases_manifest"])
        image, sha = runner.load_image_manifest()
        self.assertEqual(sha, runner.PINS_V2["image_manifest"])
        self.assertEqual(image["candidate_source_commit"], runner.SOURCE_COMMIT)
        self.assertEqual(image["build"]["executed"], False)
        self.assertEqual(image["large_image_imported"], False)

    def test_px_store_binding_parses_graphroot_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "storage.conf"
            conf.write_text('[storage]\ngraphroot = "/workspace/px/store"\n')
            digest = runner.sha256(conf)
            got = runner.verify_px_store_binding(conf, expected_sha=digest)
            self.assertEqual(got["graphroot"], "/workspace/px/store")
            with self.assertRaises(ValueError):
                runner.verify_px_store_binding(conf, expected_sha="0" * 64)
            with self.assertRaises(ValueError):
                runner.verify_px_store_binding(
                    conf, expected_sha=digest, expected_graphroot="/other")
            conf.unlink()
            with self.assertRaises(ValueError):
                runner.verify_px_store_binding(conf, expected_sha=digest)

    def test_image_contract_requires_labels_and_one_layer_overlay(self):
        manifest, _ = runner.load_image_manifest()
        parent_layers = ["p1", "p2"]
        child_layers = ["p1", "p2", "binary"]
        labels = dict(manifest["expected_labels"])

        def inspect(image, fmt):
            outputs = {
                "{{.Id}}": "sha256:" + IMAGE,
                "{{json .Config.Labels}}": json.dumps(labels),
                "{{json .RootFS.Layers}}": json.dumps(child_layers
                                                      if image == IMAGE
                                                      else parent_layers),
            }
            return 0, outputs[fmt]

        # Synthetic env: the production gate compares the selector to the
        # pinned store path string, without needing a private host file.
        pinned_env = {"CONTAINERS_STORAGE_CONF":
                      runner.SHARED_PX_BOUNDARY["storage_conf"]}
        result = runner.verify_image_contract(
            IMAGE, runner.SOURCE_COMMIT, env=pinned_env, inspect=inspect,
            image_manifest=manifest)
        self.assertEqual(result["parent"], runner.PARENT_IMAGE)

        bad_labels = dict(labels)
        bad_labels["org.ottojung.ivanka.source-commit"] = "wrong"
        def bad_inspect(image, fmt):
            outputs = {
                "{{.Id}}": "sha256:" + IMAGE,
                "{{json .Config.Labels}}": json.dumps(bad_labels),
                "{{json .RootFS.Layers}}": json.dumps(child_layers
                                                      if image == IMAGE
                                                      else parent_layers),
            }
            return 0, outputs[fmt]
        with self.assertRaises(ValueError):
            runner.verify_image_contract(
                IMAGE, runner.SOURCE_COMMIT, env=pinned_env,
                inspect=bad_inspect, image_manifest=manifest)

        with self.assertRaises(ValueError):
            runner.verify_image_contract(
                runner.PARENT_IMAGE, runner.SOURCE_COMMIT, env=pinned_env,
                inspect=inspect, image_manifest=manifest)

    def test_operator_slot_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slot.json"
            with self.assertRaises(ValueError):
                runner.verify_operator_slot(runner.PENDING_SLOT, path=path)
            bindings = {"source_commit": runner.SOURCE_COMMIT, "image": "i" * 64,
                        "cases_sha256": "c" * 64, "owner": "owner",
                        "evidence_root": "/workspace/evidence"}
            path.write_text(json.dumps(dict({
                "schema": "ivanka.p1.operator-slot.v1",
                "slot": "slot-abc", "expires_utc": 9999999999,
            }, **bindings)))
            self.assertEqual(runner.verify_operator_slot(
                "slot-abc", path=path, wall=lambda: 1, **bindings)["slot"], "slot-abc")
            with self.assertRaises(ValueError):
                runner.verify_operator_slot("other", path=path, wall=lambda: 1,
                                            **bindings)
            with self.assertRaises(ValueError):
                runner.verify_operator_slot("slot-abc", path=path,
                                            wall=lambda: 99999999999, **bindings)
            with self.assertRaises(ValueError):
                runner.verify_operator_slot("slot-abc", path=path,
                                            wall=lambda: 1, image="x" * 64,
                                            source_commit=bindings["source_commit"],
                                            cases_sha256=bindings["cases_sha256"],
                                            owner=bindings["owner"])


class SharedBoundaryTests(unittest.TestCase):
    """Fail-closed proof that exclusion is shared with PX, never pilot-private."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".global-worker.lock").write_text("")
        (self.root / ".worker-lease.jsonl").write_text("")
        (self.root / "storage.conf").write_text(
            '[storage]\ngraphroot = "/workspace/px/store"\n')
        self.exp = {
            "worker_root": str(self.root),
            "global_lock": str(self.root / ".global-worker.lock"),
            "lease_root": str(self.root),
            "lease_journal": str(self.root / ".worker-lease.jsonl"),
            "storage_conf": str(self.root / "storage.conf"),
            "storage_conf_sha256": runner.sha256(self.root / "storage.conf"),
            "graphroot": "/workspace/px/store",
            "watchdog_alive": str(self.root / ".watchdog-alive.json"),
        }

    def proof(self, **kw):
        values = {"lock": self.exp["global_lock"],
                  "lease_root": self.exp["lease_root"],
                  "watchdog_path": self.exp["watchdog_alive"],
                  "storage_conf": self.exp["storage_conf"],
                  "graphroot": self.exp["graphroot"]}
        values.update(kw)
        return runner.verify_shared_px_boundary(expected=self.exp, **values)

    def test_real_shared_boundary_is_accepted(self):
        got = self.proof()
        self.assertTrue(got["shared"])
        self.assertEqual(got["graphroot"], "/workspace/px/store")
        self.assertFalse(got["watchdog_alive_present"])
        self.assertFalse(got["kernel_enforcement"])

    def test_pilot_private_lock_fails_closed(self):
        with self.assertRaises(ValueError):
            self.proof(lock="/workspace/ivanka-p1-pilot-950fe331-20261126/pilot.lock")

    def test_private_lease_root_fails_closed(self):
        priv = self.root / "p1-prospective-leases"
        priv.mkdir()
        (priv / ".worker-lease.jsonl").write_text("")
        with self.assertRaises(ValueError):
            self.proof(lease_root=str(priv))

    def test_wrong_watchdog_alive_path_fails_closed(self):
        with self.assertRaises(ValueError):
            self.proof(watchdog_path=str(self.root / "private-alive.json"))

    def test_foreign_graphroot_fails_closed(self):
        with self.assertRaises(ValueError):
            self.proof(graphroot="/workspace/other/store")

    def test_drifted_storage_conf_pin_fails_closed(self):
        self.exp["storage_conf_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.proof()

    def test_symlinked_lock_fails_closed(self):
        other = self.root / "elsewhere.lock"
        other.write_text("")
        link = self.root / ".global-worker.lock"
        link.unlink()
        link.symlink_to(other)
        with self.assertRaises(ValueError):
            self.proof()

    def test_missing_lease_journal_fails_closed(self):
        (self.root / ".worker-lease.jsonl").unlink()
        with self.assertRaises(ValueError):
            self.proof()


class RunCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.case_dir, self.hashes = make_case_dir(self.data)
        self.out = self.root / "out"
        self.out.mkdir()
        self.timer = self.root / "timer.py"
        self.timer.write_text("print('timer')\n")
        self.stop_path = self.root / "STOP"
        self.lease_root = self.root / "leases"
        self.lock_path = self.root / "pilot.lock"
        self.env = {}

    def _run_case(self, **overrides):
        destination = self.out / "equal_strains-s000"

        def spawn_side_effect(cmd, env=None, stdout=None, stderr=None):
            proc = FakePopen(cmd, env=env, stdout=stdout, stderr=stderr)
            (destination / "timing.json").write_text(json.dumps({
                "timing_origin": "micall_in_container_monotonic_v1",
                "exit_code": 0, "seconds": 12.5,
            }))
            return proc

        kwargs = dict(
            case_id="equal_strains-s000", role="residual",
            case_dir=self.case_dir, destination=destination,
            image=IMAGE, commit=runner.SOURCE_COMMIT, timer=self.timer,
            env=self.env, owner="test-owner", lock_path=str(self.lock_path),
            stop_path=str(self.stop_path), lease_root=str(self.lease_root),
            disk_path=str(self.root), case_hashes=self.hashes,
            watchdog_ready=lambda: {"ready": True, "identity_bound": True,
                                    "pid_ns": 7, "starttime": 5},
            watchdog_path=self.root / "alive.json",
            watchdog_graphroot="/workspace/px/store",
            watchdog_snapshot=fake_snapshot,
            disk_usage=lambda p: type("U", (), {"free": 10 ** 12})(),
            bind_container=fake_bind, stop_cid_fn=fake_stop,
            snapshot=fake_snapshot, clock=lambda: 0.0,
            sleep=lambda _: None, audit=lambda e: e,
        )
        kwargs.update(overrides)
        metrics = {
            "score": 9900.0,
            "score_origin": "micall_final_max_abundant_truths_balanced_v2",
            "dominant_exact": True,
            "source": {"per_truth": {"truth_0": {
                "score": 950, "length": 1000, "fraction": 0.95}}},
        }
        with (
            mock.patch.object(runner.subprocess, "Popen",
                              side_effect=spawn_side_effect),
            mock.patch.object(runner, "evaluate_final_alignment",
                              return_value=metrics),
            mock.patch.object(runner, "_public_diagnostics",
                              return_value={"ok": True}),
            mock.patch.object(runner.p1_harness.binding, "inspect_pid",
                              return_value=100),
        ):
            return runner.run_case(**kwargs)

    def test_success_case_receipt_and_guard_fields(self):
        row = self._run_case()
        self.assertEqual(row["result"]["status"], "success")
        self.assertEqual(row["role"], "residual")
        self.assertEqual(row["guard"]["heartbeat"], "guard_owned_real_emitter")
        self.assertFalse(row["result"]["truth_used_at_assembly_time"])
        case = json.loads((self.out / "equal_strains-s000" / "case.json").read_text())
        self.assertEqual(case["result"]["status"], "success")

    def test_watchdog_readiness_required(self):
        row = self._run_case(watchdog_ready=lambda: (_ for _ in ()).throw(
            GuardExceeded("watchdog_unavailable")))
        self.assertEqual(row["result"]["status"], "failed")
        self.assertEqual(row["result"]["guard_error"], "watchdog_unavailable")
        self.assertIsNone(row["result"]["exit_code"])

    def test_stop_owner_mismatch_fails_closed(self):
        self.stop_path.write_text("someone-else\n")
        row = self._run_case()
        self.assertEqual(row["result"]["status"], "failed")
        self.assertEqual(row["result"]["guard_error"], "stop_owner_unauthorized")

    def test_absolute_limits_passed_and_no_heartbeat_override(self):
        captured = {}
        real = runner.p1_harness.run_prospective

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return real(*args, **kwargs)

        with mock.patch.object(runner.p1_harness, "run_prospective",
                               side_effect=spy):
            self._run_case()
        self.assertEqual(captured["limit"], MEMORY_BYTES)
        self.assertEqual(captured["wall_seconds"], WALL_CAP_SECONDS)
        self.assertEqual(captured["disk_reserve_bytes"], 32 * 1024 ** 3)
        self.assertNotIn("heartbeat", captured)
        self.assertEqual(captured["watchdog_graphroot"], "/workspace/px/store")

    def test_no_truth_at_assembly_time(self):
        events = []

        def record_eval(*args, **kwargs):
            events.append("score")
            return {"score": 9900.0,
                    "score_origin": "micall_final_max_abundant_truths_balanced_v2",
                    "dominant_exact": True,
                    "source": {"per_truth": {"t": {"score": 950}}}}

        def fake_spawn(cmd, env=None, stdout=None, stderr=None):
            events.append("spawn")
            proc = FakePopen(cmd, env=env, stdout=stdout, stderr=stderr)
            (self.out / "equal_strains-s000" / "timing.json").write_text(
                json.dumps({"timing_origin": "micall_in_container_monotonic_v1",
                            "exit_code": 0, "seconds": 12.5}))
            return proc

        destination = self.out / "equal_strains-s000"
        with mock.patch.object(runner.subprocess, "Popen", side_effect=fake_spawn), \
             mock.patch.object(runner, "evaluate_final_alignment",
                               side_effect=record_eval), \
             mock.patch.object(runner, "_public_diagnostics", return_value={}), \
             mock.patch.object(runner.p1_harness.binding, "inspect_pid",
                               return_value=100):
            row = runner.run_case(
                case_id="equal_strains-s000", role="residual",
                case_dir=self.case_dir, destination=destination,
                image=IMAGE, commit=runner.SOURCE_COMMIT, timer=self.timer,
                env=self.env, owner="test-owner", lock_path=str(self.lock_path),
                stop_path=str(self.stop_path), lease_root=str(self.lease_root),
                disk_path=str(self.root), case_hashes=self.hashes,
                watchdog_ready=lambda: {"ready": True, "identity_bound": True,
                                        "pid_ns": 7, "starttime": 5},
                watchdog_path=self.root / "alive.json",
                watchdog_graphroot="/workspace/px/store",
                watchdog_snapshot=fake_snapshot,
                disk_usage=lambda p: type("U", (), {"free": 10 ** 12})(),
                bind_container=fake_bind, stop_cid_fn=fake_stop,
                snapshot=fake_snapshot, clock=lambda: 0.0,
                sleep=lambda _: None, audit=lambda e: e)
        self.assertEqual(row["result"]["status"], "success")
        self.assertLess(events.index("spawn"), events.index("score"))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "evidence"

    def args(self):
        return mock.Mock(
            data=self.root / "data", frozen_results=self.root / "frozen.jsonl",
            timer=self.root / "timer.py", out=self.out, image=IMAGE,
            commit=runner.SOURCE_COMMIT, storage_conf=self.root / "storage.conf",
            lock=runner.DEFAULT_LOCK, stop=runner.DEFAULT_STOP,
            lease_root=runner.DEFAULT_LEASE_ROOT, disk_path=self.root,
            watchdog_path=self.root / "alive.json", owner="test-owner",
            cases=None, check=True, armed=False, slot=runner.PENDING_SLOT)

    def test_check_mode_writes_prepared_manifest_without_spawn(self):
        args = self.args()
        graphroot = "/workspace/px/store"
        with mock.patch.object(runner, "verify_pins", return_value=True), \
             mock.patch.object(runner, "pinned_podman_env",
                               return_value={"CONTAINERS_STORAGE_CONF": "/pinned"}), \
             mock.patch.object(runner, "verify_px_store_binding",
                               return_value={"storage_conf": str(args.storage_conf),
                                             "storage_conf_sha256": "f" * 64,
                                             "graphroot": graphroot}), \
             mock.patch.object(runner, "verify_shared_px_boundary",
                               return_value={"shared": True}), \
             mock.patch.object(runner, "verify_image_contract",
                               return_value={"labels": {}, "parent": runner.PARENT_IMAGE}), \
             mock.patch.object(runner, "verify_image_layer_contract",
                               return_value={"verified": True, "entries": {}}), \
             mock.patch.object(runner, "_disk_free", return_value=33 * 1024 ** 3), \
             mock.patch.object(runner.subprocess, "Popen",
                               side_effect=AssertionError("spawn in check mode")):
            summary = runner.run(args, disk_usage_fn=lambda p: 33 * 1024 ** 3,
                                 live_watchdog_check=lambda *a, **k: {"ready": True})
        self.assertFalse(summary["spawned"])
        manifest = json.loads((self.out / "prepared_manifest.json").read_text())
        self.assertFalse(manifest["spawned"])
        self.assertFalse(manifest["qualified"])
        self.assertEqual(manifest["storage"]["graphroot"], graphroot)
        self.assertEqual(manifest["design"]["residual"],
                         ["equal_strains-s000", "equal_strains-s002",
                          "equal_strains-s006", "equal_strains-s015"])
        self.assertEqual(len(manifest["design"]["control"]), 2)
        self.assertEqual(manifest["disk_admission"]["required_free_bytes"],
                         33 * 1024 ** 3)
        self.assertIn("NO-GO", manifest["guard_status"])
        self.assertFalse(manifest["truth_used_at_assembly_time"])

    def test_disk_shortfall_blocks_preparation(self):
        args = self.args()
        with mock.patch.object(runner, "verify_pins", return_value=True), \
             mock.patch.object(runner, "pinned_podman_env",
                               return_value={"CONTAINERS_STORAGE_CONF": "/pinned"}), \
             mock.patch.object(runner, "verify_px_store_binding",
                               return_value={"graphroot": "/workspace/px/store",
                                             "storage_conf": str(self.root / "storage.conf")}), \
             mock.patch.object(runner, "verify_shared_px_boundary",
                               return_value={"shared": True}), \
             mock.patch.object(runner, "verify_image_contract", return_value={}), \
             mock.patch.object(runner, "verify_image_layer_contract",
                               return_value={"verified": True}), \
             mock.patch.object(runner, "_disk_free", return_value=32 * 1024 ** 3):
            with self.assertRaises(ValueError):
                runner.prepare(args, disk_usage_fn=lambda p: 32 * 1024 ** 3)


class PhysicalCanaryTests(unittest.TestCase):
    def test_staging_keeps_truth_out_and_pins_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reads = root / "src"
            reads.mkdir()
            (reads / "r1.fastq.gz").write_bytes(b"PR1")
            (reads / "r2.fastq.gz").write_bytes(b"PR2")
            spec = {"r042": {
                "reads_dir": str(reads),
                "r1": "r1.fastq.gz", "r2": "r2.fastq.gz",
                "r1_sha256": runner.sha256(reads / "r1.fastq.gz"),
                "r2_sha256": runner.sha256(reads / "r2.fastq.gz"),
            }}
            dest, hashes = runner.stage_physical_canary(root / "canary", spec)
            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertIsNone(manifest["hidden_truth_file"])
            self.assertEqual(len(hashes), 2)
            cmd = runner.build_command(dest, root / "out", IMAGE,
                                       root / "timer.py", "name", "/cidfile")
            runner.assert_reference_blind(cmd)


if __name__ == "__main__":
    unittest.main()
