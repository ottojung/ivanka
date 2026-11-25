"""Regression: transient unreadable /proc record is measurement_unavailable.

A bound process may be present in /proc but temporarily unreadable; the guard
must not treat that null observation as identity loss while the launcher is
still running. Missing or readable-but-wrong identity remains fail-closed.
"""
import unittest

from assembler_bench import px_cohort_scheduler as sched
from fail_closed_guard import identity
from fail_closed_guard.errors import GuardExceeded
from fail_closed_guard.watch import watch_bound


def rec(pid, ppid, rss, *, start=100, ns=7, cmd="x"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "starttime": start,
            "pid_ns": ns, "cmdline_sha": cmd, "cgroup": ""}


class UnreadableBoundIdentityTests(unittest.TestCase):
    def test_unreadable_bound_pid_is_measurement_unavailable(self):
        finger = identity.bind(rec(100, 0, 1024))
        table = {100: {"pid": 100, "ppid": None, "rss": None,
                       "starttime": None, "pid_ns": None,
                       "cmdline_sha": None, "cgroup": None}}
        with self.assertRaises(GuardExceeded) as caught:
            identity.locate(finger, table, bound_pid=100)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_missing_bound_pid_still_identity_lost(self):
        finger = identity.bind(rec(100, 0, 1024))
        with self.assertRaises(GuardExceeded) as caught:
            identity.locate(finger, {}, bound_pid=100)
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_readable_wrong_identity_still_identity_lost(self):
        finger = identity.bind(rec(100, 0, 1024))
        table = {100: rec(100, 0, 1024, start=999, cmd="other")}
        with self.assertRaises(GuardExceeded) as caught:
            identity.locate(finger, table, bound_pid=100)
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_watch_bound_unreadable_bound_pid_is_measurement_unavailable(self):
        finger = identity.bind(rec(100, 0, 1024))
        snaps = [
            {100: rec(100, 0, 1024)},
            {100: {"pid": 100, "ppid": None, "rss": None,
                   "starttime": None, "pid_ns": None,
                   "cmdline_sha": None, "cgroup": None}},
        ]
        it = iter(snaps)

        def take():
            try:
                return next(it)
            except StopIteration:
                return snaps[-1]

        with self.assertRaises(GuardExceeded) as caught:
            watch_bound({"cid": "c" * 64, "pid": 100, "fingerprint": finger},
                        limit=4_000_000_000, wall_seconds=100,
                        running=lambda: True, snapshot=take,
                        measure=lambda: {}, stop=lambda cid: {"cid": cid},
                        clock=lambda: 0.0, sleep=lambda _: None)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_guard_identity_reasons_are_infra_retryable(self):
        self.assertIn("identity_lost", sched.FAILURE_REASONS)
        self.assertIn("binding_unavailable", sched.FAILURE_REASONS)
        self.assertIn("identity_lost", sched.INFRASTRUCTURE_FAILURE_REASONS)
        self.assertIn("binding_unavailable",
                      sched.INFRASTRUCTURE_FAILURE_REASONS)
