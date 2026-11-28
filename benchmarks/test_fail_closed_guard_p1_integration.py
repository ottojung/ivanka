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
                               teardown, tree, watch, watchdog)
from fail_closed_guard.errors import GuardExceeded, TeardownError

CID = "a" * 64
CID_B = "b" * 64


class PollLauncher:
    """Injected poll seam (never an exact returned handle to signal)."""

    def poll(self):
        return None


class LauncherHandle:
    """Exact spawn result with a real PGID identity and reap seam."""

    def __init__(self, pid=400):
        self.pid = pid
        self.waited = []

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.waited.append(timeout)
        return 0


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
             deadline_utc=None, clock=None, sleep=None, launcher=None,
             wall_seconds=30, interval=0.5, running=None, snapshot=None,
             bind_container=None, stop_cid=None):
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
            limit=4_000_000, wall_seconds=wall_seconds,
            deadline_utc=deadline_utc,
            running=running or (lambda: next(ticks, None) is not None),
            measure=lambda: True,
            snapshot=snapshot if snapshot is not None else (lambda: self.table),
            clock=clock if clock is not None else (lambda: 0),
            sleep=sleep if sleep is not None else (lambda _: None),
            attestation=attestation,
            bind_container=(self._binder if bind_container is None
                            else bind_container),
            stop_cid=self._stopper if stop_cid is None else stop_cid,
            launcher=launcher, interval=interval)

    def test_pre_spawn_order_watchdog_disk_then_spawn_then_bind(self):
        outcome = self._run()
        self.assertEqual(outcome["status"], "completed")
        acquired = [event for event in lease.events(self.root)
                    if event.get("state") == "active"]
        self.assertTrue(acquired)
        # Readiness is checked at admission and again on every watched sample.
        self.assertGreaterEqual(len(self.calls["watchdog"]), 1)
        self.assertEqual(self.calls["watchdog"][0], "ready")
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

    def test_delayed_cidfile_binds_after_async_write(self):
        cidfile_holder = {}

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            cidfile_holder["path"] = cidfile
            # Podman writes --cidfile asynchronously; simulate delayed write.

        class Proc:
            def poll(self):
                return None

        now = [0.0]

        def clock():
            return now[0]

        def sleep(seconds):
            now[0] += seconds
            if now[0] >= 0.5 and "path" in cidfile_holder:
                Path(cidfile_holder["path"]).write_text(CID + "\n")

        with patch("fail_closed_guard.p1_harness.natural_exit.wait_and_attest",
                   return_value={"cid": CID, "launcher_result": 0,
                                 "natural_exit_confirmed": True}):
            outcome = self._run(spawn=spawn, launcher=Proc(), clock=clock,
                                sleep=sleep, wall_seconds=30)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(self.calls["bind"], [CID])
        self.assertGreaterEqual(len(self.calls["watchdog"]), 2)
        self.assertGreaterEqual(len(self.calls["disk"]), 2)

    def test_launcher_exit_before_cid_fails_closed(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return 1

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc())
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.calls["bind"], [])
        self.assertEqual(self.calls["stop"], [])
        self.assertTrue(any(e.get("event") == "bind_unavailable"
                            for e in lease.events(self.root)))
        self.assertTrue(any(e.get("state") == "active"
                            for e in lease.events(self.root)))

    def test_malformed_cidfile_fails_closed_without_retry(self):
        sleeps = []

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            Path(cidfile).write_text("not-a-cid\n")

        class Proc:
            def poll(self):
                return None

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(),
                      sleep=lambda s: sleeps.append(s))
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(sleeps, [])
        self.assertEqual(self.calls["bind"], [])
        self.assertEqual(self.calls["stop"], [])

    def test_symlink_cidfile_fails_closed_without_retry(self):
        sleeps = []

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            target = Path(self.root) / "target.cid"
            target.write_text(CID + "\n")
            os.symlink(target, cidfile)

        class Proc:
            def poll(self):
                return None

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(),
                      sleep=lambda s: sleeps.append(s))
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(sleeps, [])
        self.assertEqual(self.calls["bind"], [])

    def test_bind_wait_deadline_fails_closed(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return None

        now = [0.0]

        def clock():
            return now[0]

        def sleep(s):
            now[0] += s

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(), clock=clock, sleep=sleep,
                      wall_seconds=1, interval=0.2)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.calls["bind"], [])
        self.assertEqual(self.calls["stop"], [])

    def test_bind_wait_heartbeat_failure_fails_closed(self):
        class BadEmitter:
            def __init__(self, *a, **k):
                pass

            def before_spawn(self):
                pass

            def refresh(self):
                raise RuntimeError("disk full")

            def bound(self, cid):
                pass

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return None

        with patch("fail_closed_guard.p1_harness.heartbeat.Emitter", BadEmitter):
            with self.assertRaises(GuardExceeded) as caught:
                self._run(spawn=spawn, launcher=Proc())
        self.assertEqual(caught.exception.reason, "heartbeat_unavailable")
        self.assertEqual(self.calls["bind"], [])

    def test_bind_wait_watchdog_failure_fails_closed(self):
        calls = {"n": 0}

        def checker():
            calls["n"] += 1
            if calls["n"] >= 2:
                return {"ready": False, "identity_bound": True}
            return {"ready": True, "identity_bound": True, "pid_ns": 7,
                    "starttime": 5, "cid": CID}

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return None

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(), watchdog_ready=checker)
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["bind"], [])

    def test_bind_wait_stop_owner_change_fails_closed(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return None

        now = [0.0]

        def clock():
            return now[0]

        def sleep(s):
            now[0] += s
            self.stop_path.write_text("other-owner\n")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(), clock=clock, sleep=sleep,
                      wall_seconds=30)
        self.assertEqual(caught.exception.reason, "stop_owner_unauthorized")
        self.assertEqual(self.calls["bind"], [])

    def test_bind_wait_disk_reserve_failure_fails_closed(self):
        calls = {"n": 0}

        def usage(_):
            calls["n"] += 1
            free = 40_000_000_000 if calls["n"] < 2 else 99
            return DiskHelper(free=free)

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)

        class Proc:
            def poll(self):
                return None

        now = [0.0]

        def clock():
            return now[0]

        def sleep(s):
            now[0] += s

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(), clock=clock, sleep=sleep,
                      disk_usage=usage, wall_seconds=30)
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.assertEqual(self.calls["bind"], [])

    def test_delayed_cid_bind_failure_tears_down_exact_cid(self):
        cidfile_holder = {}

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            cidfile_holder["path"] = cidfile

        class Proc:
            def poll(self):
                return None

        now = [0.0]

        def clock():
            return now[0]

        def sleep(s):
            now[0] += s
            if "path" in cidfile_holder and not Path(
                    cidfile_holder["path"]).exists():
                Path(cidfile_holder["path"]).write_text(CID + "\n")

        def bad_binder(cid, env, snapshot=None):
            self.calls["bind"].append(cid)
            raise GuardExceeded("identity_lost")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=Proc(), clock=clock, sleep=sleep,
                      bind_container=bad_binder)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls["bind"], [CID])
        self.assertEqual(self.calls["stop"], [CID])


class P1HarnessStartupAbortTests(P1HarnessLifecycleTests):
    """Post-spawn failures never abandon a live exact CID or release a lease."""

    def spawn_with_cid(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            Path(cidfile).write_text(CID + "\n")
        return spawn

    def abort_events(self):
        return [event for event in lease.events(self.root)
                if event.get("event") == "startup_abort"]

    def assert_no_release(self):
        journal = lease.events(self.root)
        self.assertNotIn("released", [e.get("state") for e in journal])
        self.assertTrue(any(e.get("state") == "active" for e in journal))

    def ready_then_unready(self):
        return iter([
            {"ready": True, "identity_bound": True, "pid_ns": 7,
             "starttime": 5, "cid": CID},
            {"ready": False, "identity_bound": True},
        ])

    def test_stop_loss_after_cid_write_removes_exact_cid(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            Path(cidfile).write_text(CID + "\n")
            self.stop_path.write_text("other-owner\n")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=PollLauncher())
        self.assertEqual(caught.exception.reason, "stop_owner_unauthorized")
        self.assertEqual(self.calls["bind"], [])
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assertTrue(event["teardown"]["fresh_absence_check"])
        self.assertEqual(event["lease_state"], "active_unreleased")
        self.assert_no_release()

    def test_watchdog_loss_after_cid_write_removes_exact_cid(self):
        states = self.ready_then_unready()
        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=self.spawn_with_cid(), launcher=PollLauncher(),
                      watchdog_ready=lambda: next(states))
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assertEqual(event["lease_state"], "active_unreleased")
        self.assert_no_release()

    def test_disk_loss_after_cid_write_removes_exact_cid(self):
        calls = {"n": 0}

        def usage(_):
            calls["n"] += 1
            return DiskHelper(free=40_000_000_000 if calls["n"] == 1 else 99)

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=self.spawn_with_cid(), launcher=PollLauncher(),
                      disk_usage=usage)
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_deadline_loss_after_cid_write_removes_exact_cid(self):
        values = iter([0.0, 40.0])

        def clock():
            return next(values, 40.0)

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=self.spawn_with_cid(), launcher=PollLauncher(),
                      clock=clock, wall_seconds=30)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["reason"], "binding_unavailable")
        self.assertTrue(any(e.get("event") == "bind_unavailable"
                            and e.get("detail") == "deadline"
                            for e in lease.events(self.root)))
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_no_late_cid_reaps_only_exact_launcher_group(self):
        handle = LauncherHandle(pid=401)
        states = self.ready_then_unready()
        bound = {"pgid": 401, "pid": 401, "stable": True,
                 "fingerprint": [5, 7]}
        def killpg(pgid, sig):
            if sig == 0:
                raise ProcessLookupError  # exact group proved gone
            return None

        with patch("fail_closed_guard.build.bind_launcher",
                   return_value=bound) as bind_launcher, \
                patch("fail_closed_guard.build.os.killpg",
                      side_effect=killpg) as killpg_mock:
            with self.assertRaises(GuardExceeded) as caught:
                self._run(spawn=lambda cidfile, env: handle,
                          watchdog_ready=lambda: next(states))
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(bind_launcher.call_count, 2)  # capture and reverify
        self.assertTrue(all(call.args == (401,)
                            and call.kwargs == {"snapshot": self.table}
                            for call in bind_launcher.call_args_list))
        self.assertEqual([call.args[0] for call in killpg_mock.call_args_list],
                         [401, 401])
        self.assertEqual(handle.waited, [5])
        self.assertEqual(self.calls["stop"], [])
        event = self.abort_events()[-1]
        self.assertEqual(event["late_cid"], "absent")
        self.assertEqual(event["late_cid_after_reap"], "absent")
        self.assertEqual(event["launcher_group"]["process_group"], 401)
        self.assertNotIn("cid", event)
        self.assert_no_release()

    def test_launcher_poll_fault_during_abort_keeps_original_failure(self):
        class BrokenHandle(LauncherHandle):
            def poll(self):
                raise RuntimeError("launcher observer unavailable")

        states = self.ready_then_unready()
        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=lambda cidfile, env: BrokenHandle(pid=403),
                      watchdog_ready=lambda: next(states))
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        event = self.abort_events()[-1]
        self.assertIn("launcher observer unavailable",
                      event["launcher_teardown_error"])
        self.assert_no_release()

    def test_late_cid_after_launcher_reap_is_removed_by_exact_cid(self):
        handle = LauncherHandle(pid=402)
        holder = {}

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            holder["cidfile"] = cidfile
            return handle

        def reap(_bound, _handle):
            Path(holder["cidfile"]).write_text(CID + "\n")
            return {"process_group": 402, "stopped": True}

        states = self.ready_then_unready()
        with patch("fail_closed_guard.build.bind_launcher",
                   return_value={"pgid": 402}), \
                patch("fail_closed_guard.build.stop_group", side_effect=reap):
            with self.assertRaises(GuardExceeded) as caught:
                self._run(spawn=spawn,
                          watchdog_ready=lambda: next(states))
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_failed_exact_teardown_is_evidence_and_never_releases(self):
        states = self.ready_then_unready()

        def bad_stop(cid):
            self.calls["stop"].append(cid)
            raise TeardownError("podman rm failed")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=self.spawn_with_cid(), launcher=PollLauncher(),
                      watchdog_ready=lambda: next(states), stop_cid=bad_stop)
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["teardown_result"], "unproven")
        self.assertIn("podman rm failed", event["teardown_error"])
        self.assert_no_release()
        evidence = watchdog.read_evidence(self.root)
        self.assertTrue(any(e.get("reason") == "watchdog_unbound"
                            and e.get("result") == "fail_closed"
                            for e in evidence))

    def test_unproven_teardown_proof_never_releases(self):
        states = self.ready_then_unready()

        def unproven_stop(cid):
            self.calls["stop"].append(cid)
            return {"cid": cid, "container_removed": True}

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=self.spawn_with_cid(), launcher=PollLauncher(),
                      watchdog_ready=lambda: next(states),
                      stop_cid=unproven_stop)
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        event = self.abort_events()[-1]
        self.assertEqual(event["teardown_result"], "unproven")
        self.assertIn("teardown_unverified", str(event["teardown_error"]))
        self.assert_no_release()

    def test_invalid_interval_refused_before_spawn(self):
        for bad in (0, -0.1, 1.5, True, float("nan")):
            with self.subTest(interval=bad):
                with self.assertRaises(GuardExceeded) as caught:
                    self._run(interval=bad)
                self.assertEqual(caught.exception.reason, "invalid_config")
                self.assertEqual(self.calls["spawn"], [])
                self.assertEqual(lease.events(self.root), [])

    def test_cid_wait_capped_at_watchdog_startup_grace(self):
        # The shared total budget is deliberately huge; only the reviewed
        # watchdog startup grace from durable acquisition may stop the wait.
        with patch.object(watchdog, "DEFAULT_STARTUP_BIND_GRACE", 0.0):
            with self.assertRaises(GuardExceeded) as caught:
                self._run(spawn=lambda cidfile, env: None,
                          launcher=PollLauncher(), wall_seconds=2400)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.calls["stop"], [])
        event = self.abort_events()[-1]
        self.assertEqual(event["reason"], "binding_unavailable")
        self.assertTrue(any(e.get("event") == "bind_unavailable"
                            and e.get("detail") == "deadline"
                            for e in lease.events(self.root)))
        self.assert_no_release()

    def test_ownership_fault_with_known_cid_never_tears_down(self):
        for problem in ("journal_unavailable", "owner_mismatch",
                        "cidfile_mismatch", "cid_mismatch"):
            with self.subTest(problem=problem):
                (self.root / lease.JOURNAL_NAME).unlink(missing_ok=True)
                states = self.ready_then_unready()
                with patch("fail_closed_guard.p1_harness._late_cid",
                           return_value=(None, problem)):
                    with self.assertRaises(GuardExceeded) as caught:
                        self._run(spawn=self.spawn_with_cid(),
                                  launcher=PollLauncher(),
                                  watchdog_ready=lambda states=states: next(states))
                self.assertEqual(caught.exception.reason, "watchdog_unbound")
                self.assertEqual(self.calls["stop"], [])
                event = self.abort_events()[-1]
                self.assertEqual(event["late_cid"], problem)
                self.assertNotIn("cid", event)
                self.assert_no_release()

    def test_known_cid_survives_cidfile_disappearing_after_read(self):
        holder = {}

        def spawn(cidfile, env):
            holder["cidfile"] = cidfile
            Path(cidfile).write_text(CID + "\n")

        def bad_binder(cid, env, snapshot=None):
            Path(holder["cidfile"]).unlink()
            raise GuardExceeded("identity_lost")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn, launcher=PollLauncher(),
                      bind_container=bad_binder)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertNotIn("late_cid", event)
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_late_cid_after_launcher_exit_is_removed_by_exact_cid(self):
        holder = {}

        class ExitedLauncher(LauncherHandle):
            def poll(self):
                holder["polls"] = holder.get("polls", 0) + 1
                if holder["polls"] >= 2:
                    Path(holder["cidfile"]).write_text(CID + "\n")
                return 0

        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            holder["cidfile"] = cidfile
            return ExitedLauncher(pid=405)

        states = self.ready_then_unready()
        with patch("fail_closed_guard.build.bind_launcher",
                   return_value={"pgid": 405}) as bind_launcher, \
                patch("fail_closed_guard.build.os.killpg") as killpg:
            with self.assertRaises(GuardExceeded) as caught:
                self._run(spawn=spawn,
                          watchdog_ready=lambda: next(states))
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        bind_launcher.assert_not_called()  # launcher exited before capture
        killpg.assert_not_called()
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertIs(event["launcher_alive"], False)
        self.assertEqual(event["late_cid"], "absent")
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_spawn_error_after_cid_write_removes_exact_cid(self):
        def spawn(cidfile, env):
            self.calls["spawn"].append(cidfile)
            Path(cidfile).write_text(CID + "\n")
            raise RuntimeError("launcher failed after writing cid")

        with self.assertRaises(GuardExceeded) as caught:
            self._run(spawn=spawn)
        self.assertEqual(caught.exception.reason, "spawn_failed")
        self.assertEqual(self.calls["stop"], [CID])
        event = self.abort_events()[-1]
        self.assertEqual(event["reason"], "spawn_failed")
        self.assertEqual(event["cid"], CID)
        self.assertEqual(event["teardown_result"], "proven")
        self.assert_no_release()

    def test_journal_cid_conflict_blocks_known_cid_fallback(self):
        ident = "p1-journal-conflict"
        cidfile = self.root / "cidfiles" / "journal.cid"
        cidfile.parent.mkdir(parents=True, exist_ok=True)
        lease.acquire(self.root, ident, "pilot", cid=CID_B, owner="real-owner",
                      cidfile=str(cidfile))
        evidence = p1_harness._startup_abort(
            self.root, ident, "real-owner", str(cidfile),
            GuardExceeded("watchdog_unbound"), stopper=self._stopper,
            snapshot=lambda: self.table, handle=None, known_cid=CID)
        self.assertEqual(self.calls["stop"], [])
        self.assertEqual(evidence["late_cid"], "cid_mismatch")
        self.assertNotIn("cid", evidence)

    def test_malformed_or_symlinked_cidfile_blocks_known_cid_fallback(self):
        base = self.root / "cidfiles"
        base.mkdir(parents=True, exist_ok=True)
        for label, prepare in (
                ("malformed", lambda p: p.write_text("not-a-cid\n")),
                ("symlink", lambda p: p.symlink_to(self.root / "other.cid"))):
            with self.subTest(label=label):
                ident = "p1-" + label
                cidfile = base / (label + ".cid")
                prepare(cidfile)
                lease.acquire(self.root, ident, "pilot", owner="real-owner",
                              cidfile=str(cidfile))
                evidence = p1_harness._startup_abort(
                    self.root, ident, "real-owner", str(cidfile),
                    GuardExceeded("watchdog_unbound"), stopper=self._stopper,
                    snapshot=lambda: self.table, handle=None, known_cid=CID)
                self.assertEqual(evidence["late_cid"],
                                 "cidfile_unavailable")
                self.assertNotIn("cid", evidence)
        self.assertEqual(self.calls["stop"], [])

    def test_late_recheck_respects_known_cid_mismatch(self):
        ident = "p1-known-mismatch"
        cidfile = self.root / "cidfiles" / "mismatch.cid"
        cidfile.parent.mkdir(parents=True, exist_ok=True)
        cidfile.write_text(CID_B + "\n")
        lease.acquire(self.root, ident, "pilot", cid=CID_B, owner="real-owner",
                      cidfile=str(cidfile))
        evidence = p1_harness._startup_abort(
            self.root, ident, "real-owner", str(cidfile),
            GuardExceeded("watchdog_unbound"), stopper=self._stopper,
            snapshot=lambda: self.table, handle=None, known_cid=CID)
        self.assertEqual(evidence["late_cid"], "cid_mismatch")
        self.assertEqual(evidence["late_cid_after_reap"], "cid_mismatch")
        self.assertNotIn("cid", evidence)
        self.assertEqual(self.calls["stop"], [])

    def test_launcher_group_reverify_mismatch_prevents_signal(self):
        ident = "p1-reverify"
        cidfile = self.root / "cidfiles" / "reverify.cid"
        cidfile.parent.mkdir(parents=True, exist_ok=True)
        lease.acquire(self.root, ident, "pilot", owner="real-owner",
                      cidfile=str(cidfile))
        captured = {"pgid": 407, "pid": 407, "fingerprint": [5, 7]}
        fresh = {"pgid": 999, "pid": 999, "fingerprint": [9, 9]}
        with patch("fail_closed_guard.build.bind_launcher",
                   side_effect=[fresh]), \
                patch("fail_closed_guard.build.stop_group") as stop_group:
            evidence = p1_harness._startup_abort(
                self.root, ident, "real-owner", str(cidfile),
                GuardExceeded("watchdog_unbound"), stopper=self._stopper,
                snapshot=lambda: self.table, handle=LauncherHandle(pid=407),
                launcher_group=captured)
        stop_group.assert_not_called()
        self.assertIn("launcher_identity_lost",
                      evidence["launcher_teardown_error"])
        self.assertEqual(self.calls["stop"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
