"""Regression: identity-safe startup binding (normal exec vs PID reuse).

The historical PX-R105 attempt-2 receipt (run-skesa-1795630266565545861.json)
recorded ``reason: identity_lost`` with an exact CID, null peak and proven
teardown, but no bound/observed fingerprint. From that evidence alone an
ordinary exec (cmdline changes, kernel task stays) cannot be distinguished
from genuine PID reuse (kernel task changes). These tests pin the source-level
contract that separates the two cases *and* prove fail-closed is not weakened.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench.exploratory_runtime import monitor
from fail_closed_guard import binding, identity, lease, startup, teardown
from fail_closed_guard.errors import GuardExceeded
from fail_closed_guard.watch import watch_bound

CID = "a" * 64


def rec(pid, ppid=0, rss=1000, *, start=100, ns=7, cmd="micall"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "starttime": start,
            "pid_ns": ns, "cmdline_sha": cmd, "cgroup": "0::/"}


class Proc:
    def poll(self):
        return None


class StartupIdentityBindingTests(unittest.TestCase):
    def bind(self, table, *, pid=9, cid_verified=True):
        return startup.bind(CID, pid, table[pid], cid_verified=cid_verified)

    def test_bind_uses_immutable_kernel_identity_not_cmdline(self):
        bound = self.bind({9: rec(9, cmd="sh -c micall")})
        self.assertTrue(bound["stable"])
        self.assertEqual(bound["pid"], 9)
        self.assertEqual(bound["starttime"], 100)
        self.assertEqual(bound["pid_ns"], 7)
        self.assertEqual(bound["fingerprint"], [100, 7])
        self.assertEqual(bound["cmdline_sha"], "sh -c micall")
        self.assertNotIn("cmdline_sha", bound["fingerprint"])
        self.assertEqual(identity.stable_fingerprint(rec(9)), (100, 7))

    def test_normal_exec_keeps_binding_and_is_recorded_as_exec(self):
        bound = self.bind({9: rec(9, cmd="sh -c micall")})
        after_exec = {9: rec(9, cmd="skesa --fastq1 a")}
        self.assertEqual(startup.locate(bound, after_exec), 9)
        seen = startup.observation(bound, after_exec)
        self.assertTrue(seen["observed"]["identity_matches"])
        self.assertTrue(seen["observed"]["cmdline_changed"])

    def test_pid_reuse_fails_closed(self):
        bound = self.bind({9: rec(9)})
        reused = {9: rec(9, start=999, cmd="unrelated")}
        with self.assertRaises(GuardExceeded) as caught:
            startup.locate(bound, reused)
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_namespace_change_fails_closed(self):
        bound = self.bind({9: rec(9, ns=7)})
        with self.assertRaises(GuardExceeded) as caught:
            startup.locate(bound, {9: rec(9, ns=8)})
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_missing_bound_pid_fails_closed(self):
        bound = self.bind({9: rec(9)})
        with self.assertRaises(GuardExceeded) as caught:
            startup.locate(bound, {})
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_unreadable_record_is_measurement_unavailable(self):
        bound = self.bind({9: rec(9)})
        unreadable = {9: {"pid": 9, "ppid": None, "rss": None,
                          "starttime": None, "pid_ns": None,
                          "cmdline_sha": None, "cgroup": None}}
        with self.assertRaises(GuardExceeded) as caught:
            startup.locate(bound, unreadable)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_cid_inspection_mismatch_fails_closed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.bind({9: rec(9)}, cid_verified=False)
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_bind_refuses_incomplete_kernel_identity(self):
        broken = rec(9)
        broken["pid_ns"] = None
        with self.assertRaises(GuardExceeded) as caught:
            startup.bind(CID, 9, broken)
        self.assertEqual(caught.exception.reason, "binding_unavailable")

    def test_bind_container_uses_stable_identity(self):
        with patch.object(binding, "inspect_pid", return_value=9):
            bound = binding.bind_container(CID, {}, snapshot={9: rec(9)})
        self.assertTrue(bound["stable"])
        self.assertEqual(bound["fingerprint"], [100, 7])
        self.assertEqual(bound["cid"], CID)


class WatchIdentityTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def stop(self, cid):
        self.calls.append(cid)
        return {"cid": cid, "container_removed": True}

    def run_watch(self, bound, snaps, *, keep_running=False, limit=1000,
                  wall=100):
        it = iter(snaps)
        used = [0]

        def take():
            used[0] += 1
            return next(it)

        def running():
            return keep_running or used[0] < len(snaps)

        return watch_bound(
            bound, limit=limit, wall_seconds=wall, running=running,
            snapshot=take, measure=lambda: {"incremental_bytes": 0},
            stop=self.stop, clock=lambda: 0.0, sleep=lambda _: None)

    def test_normal_exec_during_watch_finishes_with_exec_evidence(self):
        bound = startup.bind(CID, 9, rec(9, cmd="sh -c micall"))
        snaps = [{9: rec(9, cmd="sh -c micall")},
                 {9: rec(9, cmd="skesa")}]
        result = self.run_watch(bound, snaps)
        self.assertEqual(result["cid"], CID)
        self.assertEqual(result["peak_rss"], 1000)
        self.assertEqual(self.calls, [CID])
        seen = result["identity_observation"]["observed"]
        self.assertTrue(seen["identity_matches"])
        self.assertTrue(seen["cmdline_changed"])

    def test_pid_reuse_during_watch_fails_closed_by_cid_only(self):
        bound = startup.bind(CID, 9, rec(9, cmd="sh -c micall"))
        snaps = [{9: rec(9, cmd="sh -c micall")},
                 {9: rec(9, start=999, cmd="unrelated")}]
        with patch.object(os, "kill", side_effect=AssertionError("bare PID kill")), \
                patch.object(os, "killpg",
                             side_effect=AssertionError("bare PGID kill")):
            with self.assertRaises(GuardExceeded) as caught:
                self.run_watch(bound, snaps, keep_running=True)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls, [CID])
        self.assertFalse(
            caught.exception.identity_observation["observed"]["identity_matches"])
        self.assertEqual(caught.exception.guard_result["cid"], CID)

    def test_teardown_calls_stop_with_cid_not_pid(self):
        bound = startup.bind(CID, 9, rec(9))
        with self.assertRaises(GuardExceeded) as caught:
            self.run_watch(bound, [{9: rec(9, rss=5000)}], limit=1000)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.calls, [CID])
        self.assertNotIn(9, self.calls)


class StartupPolicyTests(unittest.TestCase):
    def test_identity_loss_at_startup_is_terminal_not_retried(self):
        cidfile = None
        with tempfile.TemporaryDirectory() as folder:
            cidfile = Path(folder) / "pilot.cid"
            cidfile.write_text(CID)
            sleeps = []

            def never_sleep(_seconds):
                sleeps.append(1)
                raise AssertionError("startup identity loss must not be retried")

            with patch.object(binding, "inspect_pid", return_value=9):
                with self.assertRaises(GuardExceeded) as caught:
                    monitor._bind_started(
                        Proc(), cidfile, {}, start=0.0, wall_seconds=30,
                        interval=0.25, clock=lambda: 0.0, sleep=never_sleep,
                        disk=lambda: None, snapshot=lambda: {})
            self.assertEqual(caught.exception.reason, "identity_lost")
            self.assertEqual(sleeps, [])

    def test_exact_cid_teardown_still_signals_no_pid(self):
        with patch.object(teardown, "_listed", side_effect=[{CID}, set()]), \
                patch.object(teardown.subprocess, "run") as runner:
            proof = teardown.stop_cid({}, CID)
        self.assertTrue(proof["container_removed"])
        self.assertEqual(runner.call_args[0][0][-1], CID)

    def test_fail_closed_reasons_remain_infra_retryable(self):
        for reason in ("identity_lost", "binding_unavailable",
                       "measurement_unavailable"):
            self.assertIn(reason, sched.FAILURE_REASONS)
            self.assertIn(reason, sched.INFRASTRUCTURE_FAILURE_REASONS)

    def test_stable_fingerprint_compatible_with_lease_cid_binding(self):
        bound = startup.bind(CID, 9, rec(9))
        with tempfile.TemporaryDirectory() as root:
            lease.bind_cid(root, "lease", CID, pid=bound["pid"],
                           fingerprint=bound["fingerprint"])
            with patch.object(binding, "command", return_value=CID + "\n"):
                report = lease.reconcile(root, {})
            self.assertEqual(report["blocked"][0]["reason"],
                             "orphan_container_alive")
            self.assertEqual(lease.latest(lease.events(root))["lease"]["cid"],
                             CID)


if __name__ == "__main__":
    unittest.main()
