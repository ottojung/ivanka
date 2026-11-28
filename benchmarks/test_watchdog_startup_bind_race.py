"""Adversarial proofs for the watchdog snapshot/inspect startup race.

Source-only: synthetic /proc tables and injected read-only ``podman inspect``
answers. No container, lease, heartbeat, STOP sentinel, receipt or live
controller is created, signalled or changed.

The operator's finding is that ``check_once`` sampled ``/proc`` before
``verify_bound`` inspected the exact CID. A controller can publish its CID
file and receive an init PID before that PID appears in the earlier table;
the old ordering then raised ``binding_unavailable``/``identity_lost`` and
tore down a healthy arm. These tests force the ordering explicitly: the
sampler returns the early table only until an exact-CID inspect has happened,
and the fresh table afterwards.
"""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import binding, heartbeat, lease, watchdog
from fail_closed_guard.errors import GuardExceeded

sys.path.insert(0, str(Path(__file__).parent))
from test_fail_closed_watchdog import (CID, GRAPHROOT, FREE, WORKER,  # noqa: E402
                                       WatchdogTests, rec)


class StartupBindRaceTests(WatchdogTests):
    """Exact-CID inspection must precede the sample used for binding."""

    def check_ordered(self, sampler, *, measure=None, max_age=10000,
                      bound_observation=None):
        """Run check_once with an ordering-aware /proc sampler."""
        def run():
            return watchdog.check_once(
                self.root, WORKER, storage_conf=self.conf, graphroot=GRAPHROOT,
                env=self.env, heartbeat_path=heartbeat.path(self.root, WORKER),
                monotonic=self.clock, wall_clock=self.wall, snapshot=sampler,
                measure=(lambda: FREE if measure is None else measure()),
                stop=self.make_stop(), rss_limit=watchdog.RSS_LIMIT,
                max_age=max_age)

        if bound_observation is None:
            return run()
        original = watchdog.verify_bound

        def wrapped(*args, **kwargs):
            observed = original(*args, **kwargs)
            bound_observation.append(observed)
            return observed

        with patch.object(watchdog, "verify_bound", side_effect=wrapped):
            return run()

    def race_sampler(self, early, fresh):
        """Early table before the first inspect, fresh table after it."""
        def take():
            inspected = any(argv[1] == "inspect" for argv in self.podman_calls)
            return dict(fresh if inspected else early)
        return take

    def early_table(self):
        """Controller present, newly issued bound PID not yet visible."""
        return {4242: rec(4242, 1, 1000, start=100)}

    def fresh_table(self, *, child_rss=500):
        return self.table(child_rss=child_rss)

    def patch_inspect(self, values):
        """Inject a read-only inspect sequence; delegate store info checks."""
        original = self.fake_command
        calls = {"n": 0}

        def command(argv, env, timeout=15):
            if argv[1] == "inspect":
                value = values[min(calls["n"], len(values) - 1)]
                calls["n"] += 1
                self.podman_calls.append(list(argv))
                if value is None:
                    raise subprocess.CalledProcessError(
                        1, argv,
                        stderr='Error: no such object: "%s"' % CID)
                return "%s %s\n" % (CID, value)
            return original(argv, env, timeout=timeout)

        return patch.object(binding, "command", side_effect=command), calls

    def test_pending_bind_with_late_pid_is_not_torn_down(self):
        """Healthy startup: CID published, PID only in the post-inspect sample."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        seen = []
        result = self.check_ordered(
            self.race_sampler(self.early_table(), self.fresh_table()),
            bound_observation=seen)
        self.assertEqual(result["result"], "observing")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])
        bound = seen[-1]
        self.assertEqual(bound["state"], "pending_bind")
        self.assertEqual(bound["pending_reason"], "startup_bind_grace")
        self.assertIs(bound["sample_diagnostic"]["sample_after_inspect"], True)

    def test_late_pid_with_published_fingerprint_still_measures(self):
        """A late /proc record for an inspected PID must not look like drift."""
        self.issue()
        self.beat()
        seen = []
        result = self.check_ordered(
            self.race_sampler(self.early_table(), self.fresh_table()),
            bound_observation=seen)
        self.assertEqual(result["result"], "observing")
        self.assertEqual(seen[-1]["rss"], 2500)
        self.assertEqual(seen[-1]["sample_diagnostic"]["second_pid"], 100)
        self.assertEqual(self.stopped, [])

    def test_bound_heartbeat_cid_pending_bind_expires_at_grace(self):
        """A published CID with no fingerprint expires at the same finite grace."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=CID)
        self.clock.advance(121)
        with self.assertRaises(GuardExceeded) as caught:
            self.check_ordered(
                self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_live_then_two_absences_is_natural_exit_without_release(self):
        """PID present, then twice absent: controller finalizes its own exit."""
        self.issue()
        self.beat(cid=CID)
        ctx, calls = self.patch_inspect([100, None, None])
        seen = []
        with ctx:
            result = self.check_ordered(
                self.race_sampler(self.early_table(), self.fresh_table()),
                bound_observation=seen)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(result["result"], "observing")
        self.assertEqual(seen[-1]["state"], "natural_exit")
        self.assertEqual(seen[-1]["absence_proof"]["inspections"], 3)
        self.assertTrue(seen[-1]["sample_diagnostic"]["natural_exit_after_live"])
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])
        self.assertEqual(
            lease.latest(lease.events(self.root))[WORKER]["state"], "active")

    def test_live_then_absence_then_reappearance_fails_closed(self):
        """No reappearance or PID drift may be read as a natural exit."""
        for third, expected in ((100, "binding_unavailable"),
                                (101, "identity_lost")):
            with self.subTest(third=third):
                self.setUp()
                self.issue()
                self.beat(cid=CID)
                ctx, calls = self.patch_inspect([100, None, third])
                with ctx:
                    with self.assertRaises(GuardExceeded) as caught:
                        self.check_ordered(
                            self.race_sampler(self.early_table(),
                                              self.fresh_table()))
                self.assertEqual(calls["n"], 3)
                self.assertEqual(caught.exception.reason, expected)
                self.assertEqual(self.stopped, [CID])
                self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_live_then_absence_with_uncertain_controller_fails_closed(self):
        """Foreign, unpublished or dead controllers never get natural exit."""
        bound = None
        for beat_cid, live in ((("f" * 64), True), (None, True), (CID, False)):
            with self.subTest(beat_cid=beat_cid, live=live):
                self.setUp()
                self.issue()
                bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
                ctx, calls = self.patch_inspect([None, None])
                with ctx:
                    with self.assertRaises(GuardExceeded) as caught:
                        watchdog.verify_bound(
                            bound, self.env, self.fresh_table(),
                            heartbeat_record={"cid": beat_cid},
                            wall=self.wall, controller_live=live,
                            first_pid=100)
                self.assertEqual(caught.exception.reason, "binding_unavailable")
                self.assertEqual(calls["n"], 1)  # no third inspect granted

    def test_reinspect_pid_change_never_gets_startup_grace(self):
        """CID -> different PID between inspections is identity drift."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        ctx, calls = self.patch_inspect([100, 101])
        with ctx:
            with self.assertRaises(GuardExceeded) as caught:
                self.check_ordered(
                    self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_absent_then_reappearing_cid_is_unavailable(self):
        """A disappearing then reappearing exact CID gets no startup grace."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        ctx, calls = self.patch_inspect([None, 100])
        with ctx:
            with self.assertRaises(GuardExceeded) as caught:
                self.check_ordered(
                    self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.stopped, [CID])
        diagnostic = caught.exception.evidence["observations"].get(
            "binding_sample") or {}
        self.assertIs(diagnostic.get("sample_after_inspect"), True)
        self.assertIsNone(diagnostic.get("first_pid"))
        self.assertEqual(diagnostic.get("second_pid"), 100)

    def test_late_pid_over_rss_limit_still_fails_closed(self):
        """Race tolerance must not relax the sampled RSS ceiling."""
        self.issue()
        self.beat()
        with self.assertRaises(GuardExceeded) as caught:
            self.check_ordered(self.race_sampler(
                self.early_table(),
                self.fresh_table(child_rss=watchdog.RSS_LIMIT + 1)))
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.stopped, [CID])

    def test_true_orphan_with_reappearing_pid_is_torn_down(self):
        """A dead controller never earns grace, even when the PID is visible."""
        self.issue()
        ctx, calls = self.patch_inspect([100, 100])
        with ctx:
            with self.assertRaises(GuardExceeded) as caught:
                self.check_ordered(
                    self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")
        self.assertEqual(calls["n"], 0)  # no inspect before the dead controller

    def test_foreign_cid_with_late_pid_gets_no_grace(self):
        """Heartbeat CID drift is identity loss, never a bind in progress."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid="f" * 64)
        with self.assertRaises(GuardExceeded) as caught:
            self.check_ordered(
                self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.stopped, [CID])

    def test_malformed_cid_never_enters_startup_grace(self):
        """A malformed CID is rejected before any inspect, sample or grace."""
        bound = {"state": "bound", "cid": "not-a-cid", "pid": None,
                 "fingerprint": None, "durable_start": 1000.0}
        with self.assertRaises(GuardExceeded) as caught:
            watchdog.verify_bound(
                bound, self.env, self.fresh_table(),
                heartbeat_record={"cid": None}, wall=self.wall,
                controller_live=True)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.podman_calls, [])

    def test_diagnostic_distinguishes_benign_race_from_true_orphan(self):
        """Receipts must tell a post-inspect sample from an unbound controller."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat(cid=None)
        seen = []
        benign = self.check_ordered(
            self.race_sampler(self.early_table(), self.fresh_table()),
            bound_observation=seen)
        diagnostic = seen[-1]["sample_diagnostic"]
        self.assertEqual(benign["result"], "observing")
        self.assertIs(diagnostic["sample_after_inspect"], True)
        self.assertEqual(diagnostic["first_pid"], 100)
        self.assertEqual(diagnostic["second_pid"], 100)

        self.stopped.clear()
        self.assertEqual(watchdog.read_evidence(self.root), [])
        heartbeat.path(self.root, WORKER).unlink()
        with self.assertRaises(GuardExceeded) as caught:
            self.check_ordered(
                self.race_sampler(self.early_table(), self.fresh_table()))
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.evidence()[-1]["action"], "teardown")
        self.assertNotIn("pending_bind",
                         caught.exception.evidence["observations"].get("bound", {}))


if __name__ == "__main__":
    unittest.main()
