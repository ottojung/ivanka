"""Regressions for garrison D1-D5 consolidated into the shared guard.

All probes use synthetic /proc trees, temp journal files and injected stop /
disk functions. No container, STOP sentinel, shared lock, frozen receipt or
live case is touched.
"""
import fcntl
import os
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fail_closed_guard import (disk, lease, p1_harness, p1_helper, proc, stop,
                               teardown, tree, watch)
from fail_closed_guard.errors import GuardExceeded

CID = "a" * 64
CID_B = "b" * 64


def rec(pid, ppid, start, ns, rss, cmd="x", cgroup="0::/"):
    return {"pid": pid, "ppid": ppid, "starttime": start, "pid_ns": ns,
            "cmdline_sha": cmd, "rss": rss, "cgroup": cgroup,
            "structural_unavailable": False}


def proof(cid=CID):
    return {"cid": cid, "container_removed": True,
            "fresh_absence_check": True, "kernel_enforcement": False}


def fake_stop(calls, fail=False, bad_proof=False):
    def stop_cid(cid):
        calls.append(cid)
        if fail:
            raise RuntimeError("podman rm failed")
        if bad_proof:
            return {"cid": cid, "container_removed": True}
        return proof(cid)
    return stop_cid


def stable_binding(table, pid=100, start=5, ns=7):
    return {"cid": CID, "pid": pid, "stable": True, "starttime": start,
            "pid_ns": ns, "fingerprint": [start, ns],
            "cmdline_sha": "x"}


class DiskHelper(SimpleNamespace):
    pass


class D1UnreadableChildTests(unittest.TestCase):
    def test_snapshot_preserves_structural_identity_of_unreadable_child(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            for pid, ppid, start in ((100, 1, 5), (101, 100, 6)):
                entry = base / str(pid)
                (entry / "ns").mkdir(parents=True)
                (entry / "stat").write_text(
                    "%d (x) S %d %s %d\n" % (pid, ppid, " ".join(["0"] * 17), start))
                (entry / "ns" / "pid").write_text("ns")
                (entry / "cmdline").write_bytes(b"x")
                (entry / "cgroup").write_text("0::/\n")
            (base / "100" / "status").write_text("Name:\tx\nVmRSS:\t1000 kB\n")

            with patch.object(proc.os, "stat",
                              return_value=SimpleNamespace(st_ino=7)):
                table = proc.snapshot(str(base))
            child = table[101]
            self.assertEqual(child["ppid"], 100)
            self.assertEqual(child["starttime"], 6)
            self.assertEqual(child["pid_ns"], table[100]["pid_ns"])
            self.assertIsNone(child["rss"])
            self.assertFalse(child["structural_unavailable"])

            group = tree.members(table, 100, None)
            self.assertEqual(group, {100, 101})
            with self.assertRaises(GuardExceeded) as caught:
                tree.rss_bytes(table, group)
            self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_watch_fails_closed_on_snapshot_unreadable_child(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000),
                 101: rec(101, 100, 6, 7, None)}
        calls = []
        with self.assertRaises(GuardExceeded) as caught:
            watch.watch_bound(
                stable_binding(table), limit=4_000_000, wall_seconds=30,
                running=lambda: True, snapshot=lambda: table,
                measure=lambda: True, stop=fake_stop(calls),
                clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")
        self.assertEqual(calls, [CID])

    def test_structurally_unknown_task_in_same_cgroup_fails_closed(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000),
                 102: {"pid": 102, "ppid": None, "starttime": None,
                       "pid_ns": None, "cmdline_sha": None, "rss": 9_000_000,
                       "cgroup": "0::/", "structural_unavailable": True}}
        with self.assertRaises(GuardExceeded) as caught:
            tree.members(table, 100, None)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")


class D2OwnerAuthorizedStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stop_path = self.root / "STOP"
        self.stop_path.write_text("hold\n")
        lease.acquire(self.root, "p1", "pilot", cid=CID, owner="real-owner")
        lease.bind_cid(self.root, "p1", CID, owner="real-owner")

    def tearDown(self):
        self.tmp.cleanup()

    def test_intruder_cannot_retire_stop(self):
        with self.assertRaises(GuardExceeded) as caught:
            stop.retire_stop(self.stop_path, proof(), owner="intruder",
                             lease_root=self.root, cid=CID)
        self.assertEqual(caught.exception.reason, "stop_owner_unauthorized")
        self.assertTrue(self.stop_path.is_file())
        self.assertEqual(
            lease.latest(lease.events(self.root))["p1"]["state"], "active")

    def test_invalid_proof_cannot_retire_stop(self):
        with self.assertRaises(GuardExceeded) as caught:
            stop.retire_stop(self.stop_path, {"cid": CID,
                                              "container_removed": True},
                             owner="real-owner", lease_root=self.root, cid=CID)
        self.assertEqual(caught.exception.reason, "teardown_unverified")
        self.assertTrue(self.stop_path.is_file())

    def test_owner_with_valid_proof_retires_and_closes_lease(self):
        audit = stop.retire_stop(self.stop_path, proof(), owner="real-owner",
                                 lease_root=self.root, cid=CID)
        self.assertEqual(audit["owner"], "real-owner")
        self.assertFalse(self.stop_path.is_file())
        self.assertEqual(
            lease.latest(lease.events(self.root))["p1"]["state"], "released")
        cleared = lease.reconcile(self.root, {}, command=lambda *_: "")
        self.assertEqual(cleared["blocked"], [])


class D3ForeignLeaseReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_foreign_release_keeps_lease_open(self):
        lease.acquire(self.root, "p1", "pilot", cid=CID, owner="dead-controller")
        lease.bind_cid(self.root, "p1", CID, owner="dead-controller")
        with self.assertRaises(GuardExceeded) as caught:
            lease.release(self.root, "p1", owner="someone-else", cid=CID_B)
        self.assertEqual(caught.exception.reason, "unauthorized_release")
        report = lease.reconcile(self.root, {}, command=lambda *_: CID)
        self.assertTrue(report["blocked"])
        self.assertEqual(report["blocked"][0]["reason"],
                         "orphan_container_alive")

    def test_forged_close_event_in_journal_is_ignored(self):
        lease.acquire(self.root, "p1", "pilot", cid=CID, owner="dead-controller")
        lease.bind_cid(self.root, "p1", CID, owner="dead-controller")
        lease.append(self.root, {"schema": lease.SCHEMA, "lease": "p1",
                                 "owner": "someone-else", "state": "released",
                                 "cid": CID_B})
        self.assertEqual(lease.latest(lease.events(self.root))["p1"]["state"],
                         "active")
        with self.assertRaises(Exception):
            lease.require_clear(self.root, {}, command=lambda *_: CID)

    def test_owner_release_clears_journal(self):
        lease.acquire(self.root, "p1", "pilot", cid=CID, owner="real-owner")
        lease.bind_cid(self.root, "p1", CID, owner="real-owner")
        lease.release(self.root, "p1", owner="real-owner", cid=CID,
                      proof=proof())
        cleared = lease.require_clear(self.root, {}, command=lambda *_: "")
        self.assertEqual(cleared["blocked"], [])


class D4DiskReserveTests(unittest.TestCase):
    def test_check_reserve_fails_closed(self):
        self.assertEqual(disk.check_reserve(
            "/tmp", 100, usage=lambda _: DiskHelper(free=101)), 101)
        with self.assertRaises(GuardExceeded) as short:
            disk.check_reserve("/tmp", 100, usage=lambda _: DiskHelper(free=99))
        self.assertEqual(short.exception.reason, "reserve_shortfall")
        with self.assertRaises(GuardExceeded) as unreadable:
            disk.check_reserve("/tmp", 100, usage=self._broken)
        self.assertEqual(unreadable.exception.reason, "measurement_unavailable")

    @staticmethod
    def _broken(_):
        raise OSError("unreadable")

    def test_watch_wires_disk_check_and_tears_down(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000)}
        calls = []
        with self.assertRaises(GuardExceeded) as caught:
            watch.watch_bound(
                stable_binding(table), limit=4_000_000, wall_seconds=30,
                running=lambda: True, snapshot=lambda: table,
                measure=lambda: True, stop=fake_stop(calls),
                clock=lambda: 0, sleep=lambda _: None,
                disk_path="/tmp", disk_reserve_bytes=100,
                disk_usage=lambda _: DiskHelper(free=99))
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.assertEqual(calls, [CID])
        self.assertEqual(
            caught.exception.guard_result["disk_observation"]["reserve_bytes"],
            100)

    def test_p1_helper_exposes_disk_check(self):
        self.assertEqual(p1_helper.check_reserve(
            "/tmp", 10, usage=lambda _: DiskHelper(free=11)), 11)


class D5TeardownProofTests(unittest.TestCase):
    def test_stop_cid_emits_fresh_absence_proof(self):
        with patch.object(teardown, "_listed") as listed, \
                patch.object(teardown.subprocess, "run") as remove:
            listed.side_effect = [{CID}, set()]
            result = teardown.stop_cid({}, CID)
        self.assertTrue(result["fresh_absence_check"])
        self.assertTrue(result["container_removed"])
        self.assertTrue(teardown.valid_proof(result, CID))
        self.assertFalse(teardown.valid_proof({}, CID))
        self.assertEqual(remove.call_count, 1)

    def test_bad_proof_on_success_path_is_teardown_unverified(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000)}
        calls = []
        ticks = iter([True, False])
        with self.assertRaises(GuardExceeded) as caught:
            watch.watch_bound(
                stable_binding(table), limit=4_000_000, wall_seconds=30,
                running=lambda: next(ticks, None) is not None,
                snapshot=lambda: table, measure=lambda: True,
                stop=fake_stop(calls, bad_proof=True), strict_proof=True,
                clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(caught.exception.reason, "teardown_unverified")
        self.assertEqual(caught.exception.teardown_error,
                         "invalid_proof_shape")
        self.assertEqual(calls, [CID])

    def test_stop_exception_becomes_guard_exceeded_with_evidence(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000)}
        ticks = iter([True, False])
        with self.assertRaises(GuardExceeded) as caught:
            watch.watch_bound(
                stable_binding(table), limit=4_000_000, wall_seconds=30,
                running=lambda: next(ticks, None) is not None,
                snapshot=lambda: table,
                measure=lambda: True, stop=fake_stop([], fail=True),
                clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(caught.exception.reason, "teardown_unverified")
        self.assertIn("podman rm failed", caught.exception.teardown_error)
        self.assertIn("teardown_error", caught.exception.guard_result)


class P1HarnessLifecycleTests(unittest.TestCase):
    """PR505 lifecycle: durable ownership precedes spawn; bind follows it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stop_path = self.root / "STOP"
        self.table = {100: rec(100, 1, 5, 7, 1_000_000)}
        self.bound = stable_binding(self.table)
        self.calls = {"spawn": [], "bind": [], "stop": [], "watchdog": [],
                      "disk": []}
        self.stop_path.write_text("real-owner\n")
        inspect = patch("fail_closed_guard.binding.inspect_pid",
                        return_value=100)
        inspect.start()
        self.addCleanup(inspect.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _spawn(self, cidfile, env):
        self.calls["spawn"].append(cidfile)
        Path(cidfile).write_text(CID + "\n")

    def _binder(self, cid, env, snapshot=None):
        self.calls["bind"].append(cid)
        result = dict(self.bound)
        result["cid"] = cid
        return result

    def _stopper(self, cid):
        self.calls["stop"].append(cid)
        return proof(cid)

    def _checker(self):
        self.calls["watchdog"].append("ready")
        return {"ready": True, "identity_bound": True, "pid_ns": 7,
                "starttime": 5, "cid": CID}

    def _usage(self):
        return lambda _: (self.calls["disk"].append("checked") or
                          DiskHelper(free=40_000_000_000))

    def _run(self, *, owner="real-owner", spawn=None, attestation=None,
             disk_usage=None, lock=None, watchdog_ready=None, lock_path=None,
             deadline_utc=None):
        ticks = iter([True, False])
        return p1_harness.run_prospective(
            owner=owner, lease_root=self.root, stop_path=self.stop_path,
            disk_path=str(self.root), spawn=spawn or self._spawn, env={},
            lock=lock if lock is not None else (
                nullcontext() if lock_path is None
                else p1_harness.ExclusiveLock(lock_path)),
            lock_path=lock_path,
            watchdog_ready=(self._checker if watchdog_ready is None
                            else watchdog_ready),
            disk_reserve_bytes=p1_harness.DEFAULT_RESERVE_BYTES,
            disk_usage=disk_usage or self._usage(),
            limit=4_000_000, wall_seconds=30, deadline_utc=deadline_utc,
            running=lambda: next(ticks, None) is not None,
            measure=lambda: True, snapshot=lambda: self.table,
            clock=lambda: 0, sleep=lambda _: None,
            attestation=attestation, bind_container=self._binder,
            stop_cid=self._stopper)

    def test_pre_spawn_order_watchdog_disk_then_spawn_then_bind(self):
        outcome = self._run()
        self.assertEqual(outcome["status"], "completed")
        acquired = [event for event in lease.events(self.root)
                    if event.get("state") == "active"]
        self.assertTrue(acquired)
        self.assertEqual(self.calls["watchdog"], ["ready"])
        # Pre-spawn reservation check happens first; the watcher re-checks it.
        self.assertEqual(self.calls["disk"][0], "checked")
        self.assertEqual(len(self.calls["spawn"]), 1)
        # The exact CID came only from the unique pinned cidfile, not a name.
        pinned = Path(self.calls["spawn"][0])
        self.assertEqual(pinned.parent.name, "cidfiles")
        self.assertEqual(pinned.read_text().strip(), CID)
        self.assertEqual(self.calls["bind"], [CID])
        self.assertTrue(outcome["result"]["teardown"]["fresh_absence_check"])
        self.assertFalse(self.stop_path.exists())

    def test_pre_spawn_disk_failure_leaves_no_spurious_lease(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(disk_usage=lambda _: DiskHelper(free=99))
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.assertEqual(self.calls["spawn"], [])
        self.assertEqual(self.calls["bind"], [])
        self.assertTrue(self.stop_path.is_file())
        self.assertEqual(lease.events(self.root), [])
        self.assertEqual(list((self.root / "cidfiles").glob("*.pinned")), [])

    def test_crash_after_spawn_before_bind_leaves_lease_open(self):
        def crash(cidfile, env):
            self._spawn(cidfile, env)
            raise RuntimeError("backend died after spawn")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=crash)
        self.assertEqual(caught.exception.reason, "spawn_failed")
        self.assertEqual(self.calls["bind"], [])
        self.assertTrue(self.stop_path.is_file())
        active = [event for event in lease.events(self.root)
                  if event.get("state") == "active"]
        self.assertTrue(active)
        self.assertEqual(active[-1]["cidfile"], self.calls["spawn"][0])
        # Reconciliation sees the container named by the pinned cidfile and
        # refuses a new admission; the crashed owner's lease is not released.
        with patch("fail_closed_guard.binding.command", return_value=CID + "\n"):
            report = lease.reconcile(self.root, {})
        self.assertTrue(report["blocked"])
        self.assertEqual(report["blocked"][0]["reason"],
                         "orphan_container_alive")

    def test_foreign_stop_refused_before_lease_or_spawn(self):
        self.stop_path.write_text("other-owner\n")
        with self.assertRaises(GuardExceeded) as caught:
            self._run(owner="real-owner")
        self.assertEqual(caught.exception.reason, "stop_owner_unauthorized")
        self.assertEqual(self.calls["spawn"], [])
        self.assertEqual(lease.events(self.root), [])
        self.assertTrue(self.stop_path.is_file())

    def test_watchdog_not_ready_refuses_spawn(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(watchdog_ready=lambda: {"ready": False,
                                              "identity_bound": True,
                                              "pid_ns": 7, "starttime": 5})
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["spawn"], [])

    def test_watchdog_without_identity_binding_refuses_spawn(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(watchdog_ready=lambda: {"ready": True,
                                              "identity_bound": False,
                                              "pid_ns": 7, "starttime": 5})
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["spawn"], [])

    def test_absolute_deadline_expired_refuses_spawn(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(deadline_utc=time.time() - 1)
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertEqual(self.calls["spawn"], [])

    def test_exclusive_lock_held_refuses_spawn(self):
        lock_path = self.root / "worker.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(GuardExceeded) as caught:
                self._run(lock_path=lock_path)
            self.assertEqual(caught.exception.reason, "lock_unavailable")
            self.assertEqual(self.calls["spawn"], [])
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_attestation_cannot_override_safety_facts(self):
        outcome = self._run(attestation={
            "kernel_enforcement": True, "enforcement": "fabricated",
            "rss_sample_scope": "launcher_process_group",
            "method": "caller-method", "version": "caller-version"})
        result = outcome["result"]
        self.assertIs(result["kernel_enforcement"], False)
        self.assertEqual(result["enforcement"], "userspace_observed")
        self.assertEqual(result["rss_sample_scope"],
                         "whole_container_process_tree")
        self.assertEqual(result["method"], "caller-method")


if __name__ == "__main__":
    unittest.main(verbosity=2)
