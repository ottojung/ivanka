"""Deterministic regressions for the reviewed watchdog race fixes.

The B1/B2 cases fail on exact watchdog head 7f613d25f and pass with the two
minimal source fixes preserved in this branch. The B3/B4 cases document
admission gaps that remain unresolved (see integration doc).
"""
import sys
import unittest
from pathlib import Path

from fail_closed_guard import heartbeat, lease
from fail_closed_guard.errors import GuardExceeded

sys.path.insert(0, str(Path(__file__).parent))
from test_fail_closed_watchdog import CID, WatchdogTests  # noqa: E402


class WatchdogRaceRegressions(WatchdogTests):
    def test_healthy_startup_cidfile_before_fingerprint_is_not_torn_down(self):
        """A live controller binding in progress keeps its container."""
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat()
        result = self.check()
        self.assertEqual(result["result"], "observing")
        self.assertEqual(result["cid"], CID)
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence(), [])

    def test_dead_controller_cidfile_only_still_requires_exact_teardown(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_expired_wall_cidfile_only_still_requires_exact_teardown(self):
        self.issue(journal_cid=False, write_cidfile=True, start=1000.0)
        self.beat()
        self.clock.advance(2500)
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertEqual(self.stopped, [CID])

    def test_heartbeat_with_foreign_cid_fails_closed(self):
        self.issue()
        self.beat(cid="f" * 64)
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["action"], "teardown")

    def test_build_admission_is_not_blocked_by_unsupported_mode(self):
        """Unresolved: the observer refuses builds but admission still spawns."""
        lease.acquire(self.root, "builder", "build")
        lease.bind(self.root, "builder", 77, [1, 2, 3])
        heartbeat.ping(self.root, wall=self.wall)
        with self.assertRaises(GuardExceeded) as caught:
            self.check("builder")
        self.assertEqual(caught.exception.reason, "unsupported_lease")
        self.assertEqual(self.evidence()[-1]["action"], "none")
        result = lease.require_clear(
            self.root, self.env, watchdog_path=heartbeat.alive_path(self.root),
            wall=self.wall)
        self.assertEqual(result["blocked"], [])

    def test_readiness_ignores_own_namespace_and_pid_identity(self):
        """Unresolved: raw read_alive has no namespace/PID binding at admission."""
        import json
        target = heartbeat.alive_path(self.root)
        target.write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": self.wall(),
            "pid": 999999, "fingerprint": [123, 456], "cmdline_sha": "x",
            "graphroot": "/foreign/store"}) + "\n")
        result = lease.require_clear(
            self.root, self.env, watchdog_path=target, wall=self.wall)
        self.assertEqual(result["blocked"], [])


if __name__ == "__main__":
    unittest.main()
