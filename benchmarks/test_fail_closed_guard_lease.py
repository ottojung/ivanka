"""Durable lease, orphan reconciliation and teardown-before-success tests."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_runtime import launch, monitor
from fail_closed_guard import binding, heartbeat, identity, lease, proc, tree
from fail_closed_guard.errors import GuardExceeded, OrphanLease
from fail_closed_guard.watch import watch_bound

CID = "a" * 64
REG = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"


def rec(pid, ppid, rss, ns=7, start=100, cmd="micall"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "pid_ns": ns,
            "starttime": start, "cmdline_sha": cmd, "cgroup": "0::/"}


class LeaseJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cidfile = self.root / "prior.cid"
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.root / "storage.conf")}

    def issue(self, cid=CID, write=True):
        lease.acquire(self.root, "prior", "pilot", cidfile=self.cidfile)
        if write:
            self.cidfile.write_text(cid if cid is not None else "")
        return cid

    def test_acquire_release_and_restart_clear(self):
        self.issue()
        lease.release(self.root, "prior", cid=CID, proof={"container_removed": True})
        with patch.object(binding, "command", side_effect=AssertionError("no ps")):
            result = lease.require_clear(self.root, self.env)
        self.assertEqual(result["blocked"], [])
        self.assertEqual(lease.latest(lease.events(self.root))["prior"]["state"],
                         "released")

    def test_crashed_launcher_active_lease_blocks_admission(self):
        self.issue()
        with patch.object(binding, "command", return_value=CID + "\n"):
            report = lease.reconcile(self.root, self.env)
            with self.assertRaises(OrphanLease) as caught:
                lease.require_clear(self.root, self.env)
        self.assertEqual(report["blocked"][0]["reason"], "orphan_container_alive")
        self.assertEqual(report["blocked"][0]["cid"], CID)
        self.assertEqual(caught.exception.report, report)
        # A failed check never rewrites ownership: no "reconciled" event.
        self.assertEqual(lease.latest(lease.events(self.root))["prior"]["state"],
                         "active")

    def test_missing_or_ambiguous_cid_blocks_admission(self):
        for write, content in ((False, None), (True, "not-a-cid"), (True, "z" * 64)):
            with self.subTest(write=write, content=content):
                self.issue(cid=content, write=write)
                with patch.object(binding, "command", return_value=""):
                    report = lease.reconcile(self.root, self.env)
                self.assertEqual(report["blocked"][0]["reason"],
                                 "ambiguous_or_missing_cid")
                lease.events(self.root)  # journal still readable
                self.cidfile.unlink(missing_ok=True)
                lease.path(self.root).unlink(missing_ok=True)

    def test_unknown_liveness_blocks_admission(self):
        self.issue()

        def unavailable(*args, **kwargs):
            raise subprocess.CalledProcessError(1, ["podman", "ps"])

        with patch.object(binding, "command", side_effect=unavailable):
            report = lease.reconcile(self.root, self.env)
            with self.assertRaises(OrphanLease):
                lease.require_clear(self.root, self.env)
        self.assertEqual(report["blocked"][0]["reason"], "liveness_unknown")

    def test_build_lease_process_liveness_and_identity(self):
        finger = identity.bind(rec(77, 0, 100, start=77))
        lease.acquire(self.root, "build", "build")
        lease.bind(self.root, "build", 77, finger)
        with patch.object(proc, "snapshot", return_value={77: rec(77, 0, 100, start=77)}):
            self.assertEqual(
                lease.reconcile(self.root, self.env)["blocked"][0]["reason"],
                "orphan_process_alive")
        with patch.object(proc, "snapshot", return_value={
                77: rec(77, 0, 100, start=77), 91: rec(91, 0, 100, start=77)}):
            self.assertEqual(
                lease.reconcile(self.root, self.env)["blocked"][0]["reason"],
                "ambiguous_identity")
        with patch.object(proc, "snapshot", return_value={}):
            report = lease.reconcile(self.root, self.env)
        self.assertEqual(report["blocked"], [])
        self.assertEqual(report["closed"][0]["reason"], "proven_absent")

    def test_tampered_journal_fails_closed(self):
        self.issue()
        journal = lease.path(self.root)
        journal.rename(self.root / "moved.jsonl")
        journal.symlink_to(self.root / "moved.jsonl")
        self.assertEqual(
            lease.reconcile(self.root, self.env)["blocked"][0]["reason"],
            "journal_unavailable")
        journal.unlink()
        journal.write_text("{not json}\n")
        self.assertEqual(
            lease.reconcile(self.root, self.env)["blocked"][0]["reason"],
            "journal_unreadable")


class WatchTeardownTests(unittest.TestCase):
    def watch(self, stop, snaps=None, running=None):
        finger = identity.bind(rec(100, 0, 1000))
        table = {100: rec(100, 0, 1000)}
        used = [0]

        def take():
            used[0] += 1
            return (snaps or [table])[min(used[0] - 1, len((snaps or [table])) - 1)]

        def live():
            used[0] += 1
            return used[0] == 1 if running is None else running()

        return watch_bound(
            {"cid": CID, "fingerprint": finger}, limit=4_000_000_000,
            wall_seconds=100, running=live, snapshot=take,
            measure=lambda: {}, stop=stop, clock=lambda: 0.0,
            sleep=lambda _: None)

    def test_teardown_proven_before_success(self):
        proof = {"cid": CID, "container_removed": True}
        result = self.watch(lambda cid: proof)
        self.assertEqual(result["teardown"], proof)
        self.assertEqual(result["enforcement"], "userspace_observed")
        self.assertFalse(result["kernel_enforcement"])

    def test_stop_failure_never_reports_success(self):
        def stop(_cid):
            raise OSError("podman rm failed")

        with self.assertRaises(GuardExceeded) as caught:
            self.watch(stop)
        self.assertEqual(caught.exception.reason, "teardown_unverified")

    def test_monitor_exit_with_live_container_still_stops_by_cid(self):
        class Stopped:
            def poll(self):
                return 0

        config = {"rss_bytes": 1000, "wall_seconds": 100, "registry": {},
                  "baseline": {}, "root": ".", "image_store": ".",
                  "workspace": "."}
        stopped = []
        with patch.object(monitor.binding, "read_cid", return_value=CID), \
                patch.object(monitor.binding, "inspect_pid", return_value=9), \
                patch.object(monitor.proc, "snapshot", return_value={9: rec(9, 0, 1)}):
            result = monitor.watch_pilot(
                Stopped(), config, cidfile=Path("x.cid"), env={},
                measure=lambda *a: {"incremental_bytes": 0},
                stop=lambda cid: stopped.append(cid) or {"removed": True},
                sleep=lambda _: None, clock=lambda: 0.0)
        self.assertEqual(stopped, [CID])
        self.assertEqual(result["teardown"], {"removed": True})

    def test_transient_disk_measurement_failure_fails_closed(self):
        class Live:
            def poll(self):
                return None

        config = {"rss_bytes": 1000, "wall_seconds": 100, "registry": {},
                  "baseline": {}, "root": ".", "image_store": ".",
                  "workspace": "."}
        stopped = []
        calls = [0]

        def measure(*args):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError("transient overlay read failure")
            return {"incremental_bytes": 0}

        with patch.object(monitor.binding, "read_cid", return_value=CID), \
                patch.object(monitor.binding, "inspect_pid", return_value=9), \
                patch.object(monitor.proc, "snapshot", return_value={9: rec(9, 0, 1)}):
            with self.assertRaises(GuardExceeded) as caught:
                monitor.watch_pilot(
                    Live(), config, cidfile=Path("x.cid"), env={}, measure=measure,
                    stop=stopped.append, sleep=lambda _: None, clock=lambda: 0.0)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")
        self.assertEqual(stopped, [])


class ExactIdentityTests(unittest.TestCase):
    def test_proc_snapshot_parses_pid_ns_starttime_and_null_rss(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = Path(folder, "123")
            (entry / "ns").mkdir(parents=True)
            fields = ["S", "1"] + ["0"] * 17 + ["55"]
            (entry / "stat").write_text(f"123 (x) {' '.join(fields)}\n")
            (entry / "ns" / "pid").write_text("")
            (entry / "cmdline").write_bytes(b"cmd\0arg")
            (entry / "cgroup").write_text("0::/\n")
            (entry / "status").write_text("Name:\tx\n")
            record = proc.snapshot(folder)[123]
            namespace_id = (entry / "ns" / "pid").stat().st_ino
        self.assertEqual(record["ppid"], 1)
        self.assertEqual(record["starttime"], 55)
        self.assertEqual(record["pid_ns"], namespace_id)
        self.assertIsNone(record["rss"])
        self.assertEqual(record["cmdline_sha"],
                         hashlib.sha256(b"cmd\0arg").hexdigest())
        # Unavailable RSS is a null observation, never a zero-byte reading.
        with self.assertRaises(GuardExceeded) as caught:
            tree.rss_bytes({123: record}, {123})
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_identity_ambiguity_and_ns_union_rss(self):
        finger = identity.bind(rec(100, 0, 1, start=100))
        with self.assertRaises(GuardExceeded) as caught:
            identity.locate(finger, {100: rec(100, 0, 1, start=100),
                                     101: rec(101, 0, 1, start=100)})
        self.assertEqual(caught.exception.reason, "identity_lost")
        table = {100: rec(100, 0, 1_000_000_000),
                 101: rec(101, 100, 1_000_000_000, start=101),
                 102: rec(102, 101, 1_000_000_000, ns=8, start=102),
                 999: rec(999, 0, 9_000_000_000, ns=8, start=5, cmd="other")}
        group = tree.members(table, 100, finger)
        self.assertEqual(group, {100, 101, 102})
        self.assertEqual(tree.rss_bytes(table, group), 3_000_000_000)
        table[102]["rss"] = None
        with self.assertRaises(GuardExceeded) as caught:
            tree.rss_bytes(table, group)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_exact_cid_inspect_rejects_mismatch(self):
        with patch.object(binding, "command", return_value=f"{CID} 555"):
            self.assertEqual(binding.inspect_pid(CID, {}), 555)
        with patch.object(binding, "command", return_value=f"b{CID[1:]} 555"):
            with self.assertRaises(GuardExceeded) as caught:
                binding.inspect_pid(CID, {})
        self.assertEqual(caught.exception.reason, "identity_lost")


class LauncherAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.policy = copy.deepcopy(checked(REG))
        self.policy["policy"]["dedicated_podman_storage_conf"] = str(
            self.root / "storage.conf")
        self.policy["policy"]["dedicated_image_store_root"] = str(self.store)
        (self.root / "storage.conf").write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "' + str(self.store / "store")
            + '"\nrunroot = "' + str(self.store / "run") + '"\n')
        base = {"schema": "ivanka.exploratory.storage-baseline.v1",
                "root": str(self.root), "image_store": str(self.store),
                "workspace": str(self.root), "base_store_bytes": 0,
                "frozen_manifest_sha256":
                    self.policy["policy"]["frozen_seven_manifest_sha256"],
                "active_job": None}
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps(base))
        self.policy["storage_baseline_sha256"] = hashlib.sha256(
            self.baseline.read_bytes()).hexdigest()
        for target, value in (
                ("assembler_bench.exploratory_runtime.setup.checked", self.policy),
                ("assembler_bench.exploratory_space.available", 100 * 1024**3)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def operate(self):
        heartbeat.ping(self.root)
        return launch.operate(REG, self.baseline, "skesa", "build",
                              [sys.executable, "-c", "print('hello')"], 1024**3)

    def test_prior_live_container_refuses_new_job(self):
        cidfile = self.root / "prior.cid"
        lease.acquire(self.root, "prior", "pilot", cidfile=cidfile)
        cidfile.write_text(CID)
        with patch.object(binding, "command", return_value=CID + "\n"):
            with self.assertRaises(OrphanLease):
                self.operate()
        self.assertEqual(list(self.root.glob("run-*.json")), [])

    def test_restart_after_release_admits_new_job(self):
        cidfile = self.root / "prior.cid"
        lease.acquire(self.root, "prior", "pilot", cidfile=cidfile)
        lease.release(self.root, "prior", cid=CID, proof={"container_removed": True})
        with patch.object(binding, "command", side_effect=AssertionError("no ps")):
            result = self.operate()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(list(self.root.glob("run-*.json"))), 1)
        self.assertEqual(lease.latest(lease.events(self.root))["prior"]["state"],
                         "released")

    def test_success_requires_proven_teardown(self):
        with patch.object(launch, "watch", return_value={
                "peak_rss": 1, "cid": None, "teardown": None}):
            result = self.operate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "teardown_unverified")
        self.assertEqual(result["lease_state"], "active_unreleased")
        latest = lease.latest(lease.events(self.root))
        self.assertTrue(latest)
        self.assertTrue(all(event["state"] == "active" for event in latest.values()))


if __name__ == "__main__":
    unittest.main()
