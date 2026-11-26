"""Deterministic interleavings of watchdog teardown and controller finalization.

No container, image, STOP sentinel, receipt or live arm is touched: podman
inspect is injected, /proc tables are synthetic and stop/receipt effects are
observed with in-memory callables. Every probe patches bare PID/PGID signals.
"""
import subprocess
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import (binding, heartbeat, lease, p1_harness,
                               teardown, watchdog)
from fail_closed_guard.errors import GuardExceeded, OrphanLease
from fail_closed_guard.watchdog_contract import (downgrade_on_watchdog_teardown,
                                                 require_watchdog_readiness)

sys.path.insert(0, str(Path(__file__).parent))
from test_fail_closed_guard_p1_integration import (CID, P1HarnessLifecycleTests)  # noqa: E402
from test_fail_closed_watchdog import (CID as W_CID, GRAPHROOT, WORKER,  # noqa: E402
                                       WatchdogTests, rec)

# The harness issue() uses this CID; keep the two modules aligned.
assert CID == W_CID


def absent_inspect(cid, *, other=False):
    """Real podman error naming the exact CID it cannot find."""
    named = "f" * 64 if other else cid
    return subprocess.CalledProcessError(
        1, ["podman", "inspect", "--format", "{{.Id}} {{.State.Pid}}", cid],
        stderr=f'Error: no such object: "{named}"')


class NaturalExitInterleavings(WatchdogTests):
    """A naturally exited CID must not become a fail-closed receipt downgrade."""

    def _inspect_absent(self, *, other=False):
        original = binding.command

        def command(argv, env, timeout=15):
            if argv[1] == "inspect":
                raise absent_inspect(CID, other=other)
            return original(argv, env, timeout=timeout)

        return command

    def test_live_controller_finalizing_absent_cid_keeps_success(self):
        self.issue()
        self.beat()
        receipt = {"status": "finished", "peak_rss": 4096}
        seen = {}

        def stop(cid):
            # The controller writes its receipt while teardown is in flight.
            seen["during"] = downgrade_on_watchdog_teardown(
                self.root, WORKER, dict(receipt))
            return {"cid": cid, "container_removed": False,
                    "fresh_absence_check": True, "method": "exact_cid_inspect",
                    "absence_proof": {"observed_absent": True}}

        with patch.object(binding, "command", side_effect=self._inspect_absent()), \
             patch("os.kill", side_effect=AssertionError("bare PID signal")), \
             patch("os.killpg", side_effect=AssertionError("bare PGID signal")):
            result = self.check(stop=stop)
        self.assertEqual(result["result"], "observing")
        self.assertEqual(result["lease_state"], "bound")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])
        self.assertNotIn("during", seen)  # no teardown was ever justified
        self.assertEqual(
            downgrade_on_watchdog_teardown(self.root, WORKER, receipt)["status"],
            "finished")

    def test_absent_cid_with_verified_live_controller_is_benign_observation(self):
        self.issue()
        self.beat()
        bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
        beat = watchdog.read_heartbeat(heartbeat.path(self.root, WORKER),
                                       monotonic=self.clock, worker=WORKER)
        with patch.object(binding, "command", side_effect=self._inspect_absent()):
            observed = watchdog.verify_bound(
                bound, self.env, self.table(), heartbeat_record=beat,
                wall=self.wall, controller_live=True)
        self.assertEqual(observed["state"], "natural_exit")
        self.assertTrue(observed["absence_proof"]["observed_absent"])
        self.assertEqual(observed["absence_proof"]["method"], "exact_cid_inspect")

    def test_absent_cid_without_live_controller_fails_closed(self):
        self.issue()
        bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
        with patch.object(binding, "command", side_effect=self._inspect_absent()):
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.verify_bound(bound, self.env, self.table(),
                                      controller_live=False)
        self.assertEqual(caught.exception.reason, "binding_unavailable")

    def test_dead_controller_with_absent_cid_still_tears_down(self):
        self.issue()
        with patch.object(binding, "command", side_effect=self._inspect_absent()):
            with self.assertRaises(GuardExceeded) as caught:
                self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_mismatched_inspect_never_reads_as_absence(self):
        self.issue()
        self.beat()
        bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
        beat = watchdog.read_heartbeat(heartbeat.path(self.root, WORKER),
                                       monotonic=self.clock, worker=WORKER)
        # An error naming a different CID is a fault, not proof our CID is gone.
        with patch.object(binding, "command",
                          side_effect=absent_inspect(CID, other=True)):
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.verify_bound(bound, self.env, self.table(),
                                      heartbeat_record=beat,
                                      controller_live=True)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")
        # Inspect output whose {{.Id}} does not match is identity_lost.
        with patch.object(binding, "command",
                          side_effect=lambda *a, **k: "f" * 64 + " 100\n"):
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.verify_bound(bound, self.env, self.table(),
                                      heartbeat_record=beat,
                                      controller_live=True)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.stopped, [])


class ProofShapeInterleavings(unittest.TestCase):
    """Only exact proven absence retires a lease; faults raise."""

    def setUp(self):
        self.env = {"CONTAINERS_STORAGE_CONF": "x"}

    def _inspect(self, value):
        def command(argv, env, timeout=15):
            if isinstance(value, Exception):
                raise value
            return value
        return command

    def test_exact_absence_is_proven(self):
        with patch.object(teardown, "command",
                          side_effect=self._inspect(absent_inspect(CID))):
            self.assertFalse(teardown._inspected(self.env, CID))

    def test_absence_uses_only_exact_unambiguous_stderr(self):
        argv = ["podman", "inspect", "--format", "{{.Id}} {{.State.Pid}}", CID]
        for detail in (
            None, "no such object", f'Error: no such object: "{"f" * 64}"',
            f'Error: no such object: "{CID}0"',
            f'Error: no such object: "{CID}"\nError: database unavailable',
            f'Error: no such object: "{"f" * 64}" (requested {CID})',
        ):
            with self.subTest(detail=detail):
                exc = subprocess.CalledProcessError(1, argv, stderr=detail)
                self.assertFalse(binding.absent_evidence(exc, CID))
        for detail in (f'Error: no such object: "{CID}"',
                       f'Error: no such container: {CID}'.encode()):
            self.assertTrue(binding.absent_evidence(
                subprocess.CalledProcessError(1, argv, stderr=detail), CID))

    def test_wrong_fields_raise_instead_of_returning_false(self):
        for value in (f"{CID}\n", f"{CID} 100 extra\n",
                      f"{'f' * 64} 100\n", f"{CID} not-a-pid\n",
                      absent_inspect(CID, other=True),
                      subprocess.CalledProcessError(1, "podman inspect",
                                                    stderr="no such object")):
            with self.subTest(value=str(value)[:60]):
                with patch.object(teardown, "command",
                                  side_effect=self._inspect(value)):
                    with self.assertRaises(teardown.TeardownError):
                        teardown._inspected(self.env, CID)

    def test_malformed_inspect_blocks_verified_teardown(self):
        bad = f"{CID}\n"
        with patch.object(teardown, "command", side_effect=self._inspect(bad)), \
             patch.object(teardown.subprocess, "run") as removed:
            with self.assertRaises(teardown.TeardownError):
                teardown.stop_verified_cid(self.env, CID)
        removed.assert_not_called()


class DecisionBeforeTeardown(WatchdogTests):
    """A real limit/failure decision is durable before the destructive action."""

    def test_rss_limit_decision_survives_receipt_written_during_teardown(self):
        self.issue()
        self.beat()
        seen = {}

        def stop(cid):
            # The receipt is finalized while teardown is in flight; the real
            # fail-closed decision must already be in the journal.
            events = self.evidence()
            seen["events"] = events
            seen["receipt"] = downgrade_on_watchdog_teardown(
                self.root, WORKER, {"status": "finished"})
            return {"cid": cid, "container_removed": True,
                    "fresh_absence_check": True, "method": "exact_cid_inspect",
                    "absence_proof": {"observed_absent": True}}

        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(child_rss=4_100_000_000)], stop=stop)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual([e["reason"] for e in seen["events"]],
                         ["observed_rss_limit"])
        self.assertEqual(seen["events"][0]["action"], "teardown")
        self.assertEqual(seen["receipt"]["status"], "failed")
        self.assertEqual(seen["receipt"]["reason"], "watchdog_fail_closed")
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_teardown_failure_after_decision_keeps_the_downgrade(self):
        self.issue()
        self.beat()

        def stop(cid):
            raise teardown.TeardownError("verification_unavailable")

        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(child_rss=4_100_000_000)], stop=stop)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.evidence()[-1]["action"], "teardown_failed")
        updated = downgrade_on_watchdog_teardown(
            self.root, WORKER, {"status": "finished"})
        self.assertEqual(updated["status"], "failed")


class FailedStateBlocksAdmission(WatchdogTests):
    """The watchdog's own stale/failed observation must close admission."""

    def _clear(self):
        with patch.object(lease, "reconcile",
                          return_value={"blocked": [], "closed": []}):
            return lease.require_clear(
                self.root, self.env,
                watchdog_path=heartbeat.alive_path(self.root),
                wall=self.wall, graphroot=GRAPHROOT)

    def test_failed_observation_withdraws_readiness_until_clean_observation(self):
        table = {4242: rec(4242, 1, 1000, start=100)}
        heartbeat.ping(self.root, storage_conf=self.conf, graphroot=GRAPHROOT,
                       env=self.env, wall=self.wall, pid=4242, table=table)
        self.assertEqual(self._clear()["blocked"], [])

        # A failed observation (here a missing controller heartbeat) must not
        # leave a fresh ALIVE record behind.
        self.issue()
        with self.assertRaises(GuardExceeded):
            self.check()
        with self.assertRaises(OrphanLease) as blocked:
            self._clear()
        self.assertEqual(blocked.exception.report["blocked"][0]["reason"],
                         "watchdog_failed")
        with self.assertRaises(GuardExceeded) as caught:
            require_watchdog_readiness(
                heartbeat.alive_path(self.root), graphroot=GRAPHROOT,
                wall=self.wall, snapshot=lambda: table)
        self.assertEqual(caught.exception.reason, "watchdog_failed")

        # A clean observation of a fresh active lease advertises readiness
        # again; the failed worker's lease stays closed.
        lease.release(self.root, WORKER, cid=CID, proof={"container_removed": True})
        self.issue("fresh")
        self.beat("fresh")
        self.check("fresh")
        self.assertEqual(self._clear()["blocked"], [])

    def test_stale_alive_record_never_admits(self):
        target = heartbeat.alive_path(self.root)
        target.write_text(__import__("json").dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": self.wall() - 1000,
            "pid": 4242, "fingerprint": [100, 7], "cmdline_sha": "x",
            "graphroot": GRAPHROOT}) + "\n")
        with self.assertRaises(OrphanLease):
            self._clear()


class ActiveControllerReadiness(P1HarnessLifecycleTests):
    """The controller re-checks observer readiness on every watched sample."""

    def test_watchdog_becoming_unready_mid_arm_fails_closed(self):
        states = iter([
            {"ready": True, "identity_bound": True, "pid_ns": 7,
             "starttime": 5, "cid": CID},
            {"ready": False, "identity_bound": True, "pid_ns": 7,
             "starttime": 5},
        ])
        checked = []

        def checker():
            checked.append("ready")
            return next(states)

        polls = iter([True, True, False])

        with self.assertRaises(GuardExceeded) as caught:
            p1_harness.run_prospective(
                owner="real-owner", lease_root=self.root,
                stop_path=self.stop_path, disk_path=str(self.root),
                spawn=self._spawn, env={}, lock=nullcontext(),
                watchdog_ready=checker,
                disk_reserve_bytes=p1_harness.DEFAULT_RESERVE_BYTES,
                disk_usage=self._usage(), limit=4_000_000, wall_seconds=30,
                running=lambda: next(polls), measure=lambda: True,
                snapshot=lambda: self.table, clock=lambda: 0,
                sleep=lambda _: None, bind_container=self._binder,
                stop_cid=self._stopper)
        self.assertEqual(caught.exception.reason, "watchdog_unbound")
        self.assertGreaterEqual(len(checked), 2)
        self.assertEqual(self.calls["stop"], [CID])


if __name__ == "__main__":
    unittest.main()
