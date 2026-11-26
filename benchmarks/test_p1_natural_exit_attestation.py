"""P1 adapters must attest natural exit by exact CID, not a lagging poll.

The shared guard accepts a vanished /proc PID as completion only when an
``attest_exit`` seam proves the exact bound CID absent and supplies a real
integer launcher result. These tests pin that contract through p1_helper and
p1_harness, including the poll-lag shape of the 17:54Z PX-R035 race, and prove
that live/unknown/unusable CID, a still-running launcher, an expired deadline
and a wrong-CID teardown cannot produce a success receipt.
"""
import time
from types import SimpleNamespace
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_runtime import monitor
from fail_closed_guard import (binding, lease, natural_exit, p1_harness,
                               p1_helper, startup, teardown)
from fail_closed_guard.errors import GuardExceeded

CID = "c" * 64
OTHER = "d" * 64
ENV = {"CONTAINERS_STORAGE_CONF": "/pinned/PX/storage.conf",
       "PX_GRAPHROOT": "/pinned/PX/store"}


def record(pid, rss=1000):
    return {"pid": pid, "ppid": 1, "starttime": 100, "pid_ns": 7,
            "cmdline_sha": "podman-run", "rss": rss, "cgroup": "0::/"}


def proof(cid, removed=True):
    return {"cid": cid, "container_removed": removed,
            "fresh_absence_check": True, "method": "exact_cid_inspect",
            "absence_proof": {"observed_absent": True},
            "kernel_enforcement": False}


class Launcher:
    """Launcher whose poll lags container exit by ``lag`` calls."""
    def __init__(self, codes):
        self.codes = list(codes)
        self.n = 0

    def poll(self):
        self.n += 1
        return self.codes[self.n - 1] if self.n <= len(self.codes) else self.codes[-1]


def ticks(values):
    seq = list(values)

    def running():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return running


class HelperAttestationTests(unittest.TestCase):
    """p1_helper.watch_p1 with an explicit launcher handle."""

    def setUp(self):
        self.calls = []
        self.snaps = 0

    def run_watch(self, *, launcher, inspect=None, snaps=None, stop=None,
                  clock=None):
        self.snaps = 0
        tables = iter(snaps if snaps is not None
                      else [{9: record(9)}, {9: record(9)}, {}])

        def take():
            self.snaps += 1
            return next(tables)

        bound = startup.bind(CID, 9, record(9))
        live = patch.object(binding, "inspect_pid_if_live",
                            side_effect=(inspect or (lambda cid, env: None)))
        live.start()
        self.addCleanup(live.stop)
        effective = stop or (lambda env, cid: (self.calls.append(cid), proof(cid))[1])
        if stop is not None:
            effective = lambda env, cid: stop(cid)
        stopped = patch.object(teardown, "stop_cid", side_effect=effective)
        stopped.start()
        self.addCleanup(stopped.stop)
        return p1_helper.watch_p1(
            bound, limit=10 ** 9, wall_seconds=100, running=ticks([True] * 8),
            measure=lambda: {"incremental_bytes": 0}, env=ENV,
            clock=clock or (lambda: 0.0), sleep=lambda _s: None,
            snapshot=take, launcher=launcher, interval=0.25)

    def test_poll_lag_makes_a_true_natural_exit(self):
        result = self.run_watch(launcher=Launcher([None, None, None, 0]))
        self.assertEqual(self.snaps, 3)
        ne = result["natural_exit"]
        self.assertEqual(ne["cid"], CID)
        self.assertEqual(ne["returncode"], 0)
        self.assertEqual(ne["method"], "exact_cid_inspect")
        self.assertTrue(ne["absence_proof"]["inspected_absent_twice"])
        self.assertEqual(self.calls, [CID])
        self.assertTrue(result["identity_observation"]["observed"]["present"])
        self.assertTrue(result["teardown"]["fresh_absence_check"])

    def test_live_cid_fails_closed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None, None, None, 0]),
                           inspect=lambda cid, env: 9)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls, [CID])
        self.assertNotIn("natural_exit", caught.exception.guard_result)

    def test_no_real_result_fails_closed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None]))
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")
        self.assertEqual(self.calls, [CID])

    def test_bool_result_is_not_a_real_launcher_result(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None, None, None, True]))
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")
        self.assertEqual(self.calls, [CID])

    def test_second_inspection_regression_never_attests(self):
        seq = iter([None, None, 9])

        def flapping(_cid, _env):
            return next(seq)

        with self.assertRaises(GuardExceeded) as caught:
            # An immediate launcher result leaves exactly one absence check in
            # wait_and_attest and two inside attest(), so the third inspection
            # is the second authoritative check.
            self.run_watch(launcher=Launcher([0]), inspect=flapping)
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")
        self.assertEqual(self.calls, [CID])

    def test_unusable_inspection_never_becomes_absence(self):
        def unusable(_cid, _env):
            raise GuardExceeded("inspection_unavailable")
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None, None, None, 0]),
                           inspect=unusable)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")
        self.assertEqual(self.calls, [CID])

    def test_deadline_stops_attestation(self):
        seq = iter([0.0, 0.0, 0.0, 0.0, 1000.0])
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None]), clock=lambda: next(seq, 1000.0))
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertEqual(self.calls, [CID])

    def test_already_expired_wall_with_real_result_never_completes(self):
        ticks = iter([0.0, 0.0, 1000.0])
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([0]),
                           clock=lambda: next(ticks, 1000.0))
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_wall_crossing_during_inspect_never_completes(self):
        now = [0.0]

        def crossing(_cid, _env):
            now[0] = 1000.0  # inspect is a blocking probe that burns the budget
            return None

        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([0]), inspect=crossing,
                           clock=lambda: now[0])
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_wrong_cid_teardown_is_never_success(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(launcher=Launcher([None, None, None, 0]),
                           stop=lambda cid: proof(OTHER))
        self.assertEqual(caught.exception.reason, "teardown_unverified")
        self.assertIsNone(caught.exception.guard_result.get("teardown"))


class DiskHelper:
    def __init__(self, free):
        self.free = free

    def __int__(self):
        return self.free


class HarnessAttestationTests(unittest.TestCase):
    """p1_harness.run_prospective with a spawn-returned launcher handle."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stop_path = self.root / "STOP"
        self.stop_path.write_text("real-owner\n")
        self.calls = []
        self.table = {9: record(9)}
        self.launcher = Launcher([None, None, None, 0])
        self.inspect_patcher = patch.object(
            binding, "inspect_pid_if_live", side_effect=lambda cid, env: None)
        self.inspect_patcher.start()
        self.addCleanup(self.inspect_patcher.stop)
        patch.object(binding, "inspect_pid", return_value=9).start()
        self.addCleanup(patch.stopall)

    def _spawn(self, cidfile, env):
        Path(cidfile).write_text(CID + "\n")
        return self.launcher

    def _binder(self, cid, env, snapshot=None):
        bound = dict(startup.bind(CID, 9, record(9)))
        bound["cid"] = cid
        return bound

    def _stopper(self, cid):
        self.calls.append(cid)
        return proof(cid)

    def _checker(self):
        return {"ready": True, "identity_bound": True, "pid_ns": 7,
                "starttime": 5, "cid": CID}

    def _run(self, *, launcher=None, inspect=None, stop=None, deadline_utc=None):
        if inspect is not None:
            self.inspect_patcher.stop()
            self.inspect_patcher = patch.object(
                binding, "inspect_pid_if_live", side_effect=inspect)
            self.inspect_patcher.start()
        snaps = iter([{9: record(9)}, {9: record(9)}, {}])

        def take():
            return next(snaps)

        return p1_harness.run_prospective(
            owner="real-owner", lease_root=self.root, stop_path=self.stop_path,
            disk_path=str(self.root), spawn=self._spawn, env=ENV,
            lock=nullcontext(), watchdog_ready=self._checker,
            disk_reserve_bytes=p1_harness.DEFAULT_RESERVE_BYTES,
            disk_usage=lambda _: DiskHelper(40_000_000_000),
            limit=4_000_000, wall_seconds=100, deadline_utc=deadline_utc,
            running=ticks([True] * 8), measure=lambda: True, snapshot=take,
            clock=lambda: 0.0, sleep=lambda _s: None, interval=0.25,
            launcher=launcher, bind_container=self._binder,
            stop_cid=stop or self._stopper)

    def test_spawn_returned_launcher_attests_poll_lag(self):
        outcome = self._run()
        self.assertEqual(outcome["status"], "completed")
        result = outcome["result"]
        self.assertEqual(result["cid"], CID)
        self.assertEqual(result["natural_exit"]["returncode"], 0)
        self.assertEqual(result["natural_exit"]["method"], "exact_cid_inspect")
        self.assertEqual(self.calls, [CID])
        self.assertFalse(self.stop_path.exists())
        self.assertEqual(outcome["stop_retired_by"], "real-owner")
        self.assertTrue(result["teardown"]["fresh_absence_check"])
        events = lease.events(self.root)
        self.assertTrue(any(e.get("state") == "active" and e.get("cid") == CID
                            for e in events))
        self.assertTrue(any(e.get("state") == "released" and e.get("cid") == CID
                            for e in events))
        self.assertFalse([e for e in lease.latest(events).values()
                          if e.get("state") not in lease.CLOSED])

    def test_explicit_launcher_is_accepted(self):
        outcome = self._run(launcher=Launcher([None, None, None, 3]))
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["result"]["natural_exit"]["returncode"], 3)

    def test_live_cid_never_reports_completed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(inspect=lambda cid, env: 9)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_no_real_launcher_result_never_reports_completed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(launcher=Launcher([None]))
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})

    def test_absolute_deadline_already_expired_with_real_result(self):
        future = time.time() + 60
        expired = time.time() + 120
        fake = SimpleNamespace(time=lambda: expired, monotonic=time.monotonic)
        with patch.object(natural_exit, "time", fake):
            with self.assertRaises(GuardExceeded) as caught:
                self._run(deadline_utc=future)
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_absolute_deadline_crossing_during_inspect(self):
        future = time.time() + 60
        holder = {"t": time.time() - 10}

        def crossing(_cid, _env):
            holder["t"] = time.time() + 120  # inspect burns the absolute budget
            return None

        fake = SimpleNamespace(time=lambda: holder["t"], monotonic=time.monotonic)
        with patch.object(natural_exit, "time", fake):
            with self.assertRaises(GuardExceeded) as caught:
                self._run(deadline_utc=future, inspect=crossing)
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_wrong_cid_teardown_is_never_completed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self._run(stop=lambda cid: proof(OTHER))
        # No verified proof -> the harness refuses to retire STOP.
        self.assertEqual(caught.exception.reason, "teardown_unverified")
        self.assertTrue(self.stop_path.exists())


class PilotMonitorDeadlineTests(unittest.TestCase):
    """PX watch_pilot must not attest a natural exit past either deadline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cidfile = Path(self.tmp.name) / "pilot.cid"
        self.cidfile.write_text(CID + "\n")
        self.calls = []

    def _run(self, *, clock, launcher, inspect=None, snaps=None):
        tables = iter(snaps if snaps is not None else [{9: record(9)}])
        with patch.object(binding, "inspect_pid", return_value=9), \
                patch.object(binding, "inspect_pid_if_live",
                             side_effect=(inspect or (lambda cid, env: None))), \
                patch.object(teardown, "stop_cid",
                             side_effect=lambda env, cid: (
                                 self.calls.append(cid), proof(cid))[1]):
            return monitor.watch_pilot(
                launcher,
                {"registry": "r", "baseline": "b", "root": "root",
                 "image_store": "s", "workspace": "w",
                 "rss_bytes": 10 ** 9, "wall_seconds": 100},
                cidfile=self.cidfile, env=ENV, interval=0.25,
                stop=lambda cid: (self.calls.append(cid), proof(cid))[1],
                snapshot=lambda: next(tables),
                measure=lambda *_a: {"incremental_bytes": 0},
                clock=clock, sleep=lambda _s: None)

    def test_expired_wall_with_real_result_is_failed_closed(self):
        ticks = iter([0.0, 0.0, 1000.0])
        with self.assertRaises(GuardExceeded) as caught:
            self._run(clock=lambda: next(ticks, 1000.0), launcher=Launcher([0]))
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])

    def test_wall_crossing_during_attest_inspection(self):
        now = [0.0]

        def crossing(_cid, _env):
            now[0] = 1000.0
            return None

        with self.assertRaises(GuardExceeded) as caught:
            self._run(clock=lambda: now[0], inspect=crossing,
                      launcher=Launcher([None, 0]),
                      snaps=[{9: record(9)}, {9: record(9)}])
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertNotIn("natural_exit", caught.exception.guard_result or {})
        self.assertEqual(self.calls, [CID])


if __name__ == "__main__":
    unittest.main()
