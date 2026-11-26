"""Focused regressions for the single integrated watchdog/P1/natural-exit branch.

Every probe is deterministic: synthetic /proc tables, temp journals and injected
stop/spawn callables. No container, image, STOP sentinel, receipt or live arm is
touched.
"""
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_runtime import launch
from fail_closed_guard import (heartbeat, lease, proc as process_snapshot,
                               p1_harness, startup, teardown, watchdog, watch)
from fail_closed_guard.errors import GuardExceeded, OrphanLease
from fail_closed_guard.watch import _valid_proof

sys.path.insert(0, str(Path(__file__).parent))
from test_exploratory_runner import REG, TestRunner  # noqa: E402
from test_fail_closed_watchdog import CID, GRAPHROOT, WatchdogTests, rec  # noqa: E402
from test_fail_closed_guard_p1_integration import P1HarnessLifecycleTests  # noqa: E402


class ArmedAdmissionClosure(WatchdogTests):
    """Armed admission binds readiness to namespace and kernel identity."""

    def _clear(self, target=None, snapshot=None):
        with patch.object(lease, "reconcile",
                          return_value={"blocked": [], "closed": []}):
            return lease.require_clear(
                self.root, self.env,
                watchdog_path=target or heartbeat.alive_path(self.root),
                wall=self.wall, graphroot=GRAPHROOT, snapshot=snapshot)

    def test_bound_watchdog_record_admits(self):
        table = {4242: rec(4242, 1, 1000, start=100)}
        heartbeat.ping(self.root, storage_conf=self.conf, graphroot=GRAPHROOT,
                       env=self.env, wall=self.wall, pid=4242, table=table)
        self.assertEqual(self._clear(snapshot=lambda: table)["blocked"], [])

    def test_foreign_namespace_record_blocks(self):
        target = heartbeat.alive_path(self.root)
        target.write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": self.wall(),
            "pid": 4242, "fingerprint": [100, 7], "cmdline_sha": "x",
            "graphroot": "/foreign/store"}) + "\n")
        with self.assertRaises(OrphanLease) as caught:
            self._clear(target=target)
        self.assertEqual(caught.exception.report["blocked"][0]["reason"],
                         "watchdog_unbound")

    def test_reused_pid_record_blocks(self):
        target = heartbeat.alive_path(self.root)
        target.write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": self.wall(),
            "pid": 999999, "fingerprint": [123, 456], "cmdline_sha": "x",
            "graphroot": GRAPHROOT}) + "\n")
        table = {4242: rec(4242, 1, 1000, start=100)}
        with self.assertRaises(OrphanLease) as caught:
            self._clear(target=target, snapshot=lambda: table)
        self.assertEqual(caught.exception.report["blocked"][0]["reason"],
                         "watchdog_unavailable")


class ProofAlignmentTests(unittest.TestCase):
    """Controller and watchdog teardown proofs meet one strict contract."""

    def test_authoritative_inspect_absence_is_valid_everywhere(self):
        proof = {"cid": CID, "container_removed": False,
                 "fresh_absence_check": True, "method": "exact_cid_inspect",
                 "absence_proof": {"observed_absent": True}}
        self.assertTrue(teardown.valid_proof(proof, CID))
        self.assertIs(teardown.require_proof(proof, CID), proof)
        self.assertTrue(_valid_proof(proof, CID, True))

    def test_bare_absence_claim_never_retires_a_lease(self):
        proof = {"cid": CID, "container_removed": False,
                 "fresh_absence_check": True}
        self.assertFalse(teardown.valid_proof(proof, CID))
        self.assertFalse(_valid_proof(proof, CID, True))
        with self.assertRaises(GuardExceeded) as caught:
            teardown.require_proof(proof, CID)
        self.assertEqual(caught.exception.reason, "teardown_unverified")

    def test_build_group_proof_remains_valid(self):
        proof = {"process_group": 77, "stopped": True}
        self.assertTrue(_valid_proof(proof, None, False))
        # Strict proof is the P1/pilot contract; build mode proves its exact
        # process group through the non-strict build watcher instead.
        self.assertFalse(_valid_proof(proof, None, True))
        self.assertFalse(_valid_proof({"process_group": 77}, None, False))

    def test_stop_verified_cid_emits_authoritative_absence(self):
        absent = subprocess.CalledProcessError(
            1, "podman inspect", stderr="no such object")
        # The watchdog removed the container first; the controller's scoped
        # inspect sees it already absent and must still emit a valid proof.
        with patch.object(teardown, "command", side_effect=[absent, absent]), \
                patch.object(teardown.subprocess, "run") as removed:
            proof = teardown.stop_verified_cid({"CONTAINERS_STORAGE_CONF": "x"},
                                               CID)
        removed.assert_not_called()
        self.assertFalse(proof["container_removed"])
        self.assertTrue(proof["fresh_absence_check"])
        self.assertTrue(teardown.valid_proof(proof, CID))


class P1HarnessClosureTests(P1HarnessLifecycleTests):
    """P1 readiness and the absolute deadline use the shared contract."""

    def test_deadline_is_derived_from_durable_lease_start(self):
        outcome = self._run()
        lease_id = next(iter(lease.latest(lease.events(self.root))))
        start = lease.acquisition_start(self.root, lease_id)
        self.assertEqual(outcome["deadline_utc"], start + 30)

    def test_watchdog_path_is_namespace_bound(self):
        target = heartbeat.alive_path(self.root)
        target.write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": time.time(),
            "pid": 4242, "fingerprint": [5, 7], "cmdline_sha": "x",
            "graphroot": "/foreign/store"}) + "\n")
        with self.assertRaises(GuardExceeded) as caught:
            p1_harness.run_prospective(
                owner="real-owner", lease_root=self.root,
                stop_path=self.stop_path, disk_path=str(self.root),
                spawn=self._spawn, env={}, lock=nullcontext(),
                watchdog_path=str(target), watchdog_graphroot="/own/store",
                disk_reserve_bytes=100, disk_usage=self._usage(),
                limit=4_000_000, wall_seconds=30,
                running=lambda: True, measure=lambda: True,
                snapshot=lambda: self.table, clock=lambda: 0,
                sleep=lambda _: None, bind_container=self._binder,
                stop_cid=self._stopper)
        self.assertEqual(caught.exception.reason, "watchdog_unbound")


class LaunchReceiptClosureTests(TestRunner):
    """Launch records cannot claim success over a watchdog teardown."""

    def test_watchdog_teardown_downgrades_finished_receipt(self):
        with patch.object(launch.time, "time_ns", return_value=12345):
            watchdog.append_evidence(self.root, {
                "schema": watchdog.SCHEMA, "worker": "skesa-12345",
                "reason": "wall_limit", "result": "fail_closed",
                "action": "teardown"})
            result = self.run_job()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "watchdog_fail_closed")
        self.assertEqual(result["watchdog_evidence"]["events"], ["wall_limit"])

    def test_armed_build_is_rejected_before_spawn(self):
        target = heartbeat.alive_path(self.root)
        target.write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": time.time(),
            "pid": 4242, "fingerprint": [7, 9], "cmdline_sha": "x",
            "graphroot": str(self.store / "store")}) + "\n")
        table = dict(process_snapshot.snapshot())
        table[4242] = {"pid": 4242, "ppid": 1, "rss": 1, "starttime": 7,
                       "pid_ns": 9, "cmdline_sha": "x", "cgroup": "0::/"}
        with patch.dict(os.environ, {"WATCHDOG_ARMED": "1"}),                 patch.object(process_snapshot, "snapshot", return_value=table):
            with self.assertRaises(GuardExceeded) as caught:
                launch.operate(REG, self.baseline, "skesa", "build",
                               [sys.executable, "-c", "print('hello')"], 1024**3)
        self.assertEqual(caught.exception.reason, "watchdog_unsupported_mode")

    def test_armed_missing_alive_fails_closed_no_fallback(self):
        from fail_closed_guard.errors import OrphanLease
        with patch.dict(os.environ, {"WATCHDOG_ARMED": "1"}):
            with self.assertRaises(OrphanLease) as caught:
                launch.operate(REG, self.baseline, "skesa", "build",
                               [sys.executable, "-c", "print('hello')"], 1024**3)
        self.assertEqual(
            caught.exception.report["blocked"][0]["reason"],
            "watchdog_unavailable")
        self.assertEqual(list(self.root.glob("run-*.json")), [])


class StoreNamespaceParsingTests(unittest.TestCase):
    def test_quoted_toml_storage_conf_matches_real_podman_format(self):
        from fail_closed_guard import store
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "storage.conf"
            graphroot = "/workspace/ivanka-exploratory-podman-20261121/store"
            conf.write_text(
                '[storage]\n'
                'driver = "overlay"\n'
                'graphroot = "%s"\n'
                'runroot = "%s/run"\n' % (graphroot, graphroot))
            env = {"CONTAINERS_STORAGE_CONF": str(conf)}
            seen = []
            def fake(argv, env, timeout=15):
                seen.append(list(argv))
                return graphroot + "\n"
            self.assertEqual(store.verify_namespace(env, graphroot, command=fake),
                             graphroot)
            self.assertEqual(seen[0][1], "info")


class StartupRaceAndNaturalExitTests(WatchdogTests):
    """The CID startup race fix and the natural-exit fix coexist on main."""

    def test_cidfile_race_then_unreadable_final_record_keeps_peak(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=CID)
        observation = self.check()
        self.assertEqual(observation["cid"], CID)
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])

        bound = startup.bind(CID, 100, rec(100, 4242, 2000, ns=99, start=50,
                                           cmd="micall"))
        snapshots = [
            {100: rec(100, 4242, 2000, ns=99, start=50, cmd="micall")},
            {100: rec(100, 4242, None, ns=None, start=None, cmd="micall")},
        ]
        stopped = []

        def stop(cid):
            stopped.append(cid)
            return {"cid": cid, "container_removed": True,
                    "fresh_absence_check": True}

        result = watch.watch_bound(
            bound, limit=4_000_000_000, wall_seconds=2400,
            running=lambda: bool(snapshots),
            snapshot=lambda: snapshots.pop(0), measure=lambda: True,
            stop=stop, clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(result["peak_rss"], 2000)
        self.assertEqual(result["cid"], CID)
        self.assertEqual(stopped, [CID])

    def test_pending_bind_allows_unpublished_heartbeat_cid_within_grace(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        # Controller is alive but has not yet published CID into heartbeat.
        self.beat(cid=None)
        result = self.check()
        self.assertEqual(result["result"], "observing")
        self.assertEqual(result["lease_state"], "bound")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])

    def test_pending_bind_unpublished_cid_outside_grace_fails_closed(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        self.clock.advance(121)
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.stopped, [CID])

    def test_pending_bind_stale_heartbeat_still_tears_down(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        self.clock.advance(31)
        with self.assertRaises(GuardExceeded) as caught:
            self.check(max_age=30, wall_seconds=2400)
        self.assertEqual(caught.exception.reason, "heartbeat_stale")
        self.assertEqual(self.stopped, [CID])


class P1HarnessReviewClosure(P1HarnessLifecycleTests):
    """Follow-up review: lock-first ordering, heartbeat and capped policy."""

    def _lease_id(self):
        return next(iter(lease.latest(lease.events(self.root))))

    def test_lock_failure_leaves_no_active_lease(self):
        lock_path = self.root / "worker.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(GuardExceeded) as caught:
                self._run(lock_path=lock_path)
            self.assertEqual(caught.exception.reason, "lock_unavailable")
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertEqual(lease.events(self.root), [])
        self.assertEqual(self.calls["spawn"], [])

    def test_watchdog_unready_leaves_no_active_lease(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(watchdog_ready=lambda: {"ready": False,
                                              "identity_bound": True,
                                              "pid_ns": 7, "starttime": 5})
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertEqual(lease.events(self.root), [])

    def test_controller_heartbeat_bound_before_watch_and_refreshable(self):
        captured = {}
        original = watch.watch_bound
        def spy(*args, **kwargs):
            captured["heartbeat"] = kwargs.get("heartbeat")
            captured["reserve"] = kwargs.get("disk_reserve_bytes")
            captured["deadline"] = kwargs.get("deadline_utc")
            return original(*args, **kwargs)
        with patch.object(watch, "watch_bound", side_effect=spy):
            outcome = self._run()
        self.assertEqual(outcome["status"], "completed")
        self.assertTrue(callable(captured["heartbeat"]))
        self.assertGreaterEqual(captured["reserve"],
                                p1_harness.DEFAULT_RESERVE_BYTES)
        ident = self._lease_id()
        record = watchdog.read_heartbeat(
            heartbeat.path(self.root, ident), worker=ident)
        self.assertEqual(record["cid"], CID)
        captured["heartbeat"]()
        refreshed = watchdog.read_heartbeat(
            heartbeat.path(self.root, ident), worker=ident)
        self.assertEqual(refreshed["cid"], CID)

    def test_caller_deadline_cannot_extend_durable_cap(self):
        outcome = self._run(deadline_utc=time.time() + 99999)
        ident = self._lease_id()
        start = lease.acquisition_start(self.root, ident)
        self.assertLessEqual(outcome["deadline_utc"], start + 30)

    def test_reinspect_pid_reuse_fails_closed_with_exact_teardown(self):
        with patch("fail_closed_guard.binding.inspect_pid",
                   side_effect=[100, 101]):
            with self.assertRaises(GuardExceeded) as caught:
                self._run()
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls["stop"], [CID])
        self.assertTrue(self.stop_path.is_file())


if __name__ == "__main__":
    unittest.main()
