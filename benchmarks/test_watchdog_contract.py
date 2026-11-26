"""Deterministic tests for the preserved integration helpers."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fail_closed_guard import heartbeat, lease, watchdog
from fail_closed_guard.errors import GuardExceeded

sys.path.insert(0, str(Path(__file__).parent))
from fail_closed_guard.watchdog_contract import (  # noqa: E402
    downgrade_on_watchdog_teardown, durable_deadline,
    require_supported_mode, require_watchdog_readiness)


def rec(pid, start, ns):
    return {"pid": pid, "starttime": start, "pid_ns": ns}


class WatchdogContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.target = heartbeat.alive_path(self.root)
        self.now = 1000.0
        self.record = {"schema": heartbeat.ALIVE_SCHEMA, "at_utc": self.now,
                       "pid": 42, "fingerprint": [7, 9], "cmdline_sha": "x",
                       "graphroot": "/own/store"}
        self.table = {42: rec(42, 7, 9)}

    def write(self, **changes):
        event = dict(self.record, **changes)
        self.target.write_text(json.dumps(event) + "\n")
        return event

    def readiness(self, **kwargs):
        return require_watchdog_readiness(
            self.target, graphroot="/own/store", wall=lambda: self.now,
            snapshot=lambda: self.table, **kwargs)

    def test_genuine_record_satisfies_pr505_shape(self):
        self.write()
        result = self.readiness()
        self.assertTrue(result["ready"])
        self.assertTrue(result["identity_bound"])
        self.assertEqual((result["starttime"], result["pid_ns"]), (7, 9))

    def test_foreign_namespace_rejected(self):
        self.write(graphroot="/foreign/store")
        with self.assertRaises(GuardExceeded) as caught:
            self.readiness()
        self.assertEqual(caught.exception.reason, "watchdog_unbound")

    def test_dead_or_reused_pid_rejected(self):
        self.write()
        with self.assertRaises(GuardExceeded) as caught:
            require_watchdog_readiness(
                self.target, graphroot="/own/store", wall=lambda: self.now,
                snapshot=lambda: {42: rec(42, 99, 9)})
        self.assertEqual(caught.exception.reason, "watchdog_unavailable")

    def test_future_and_stale_rejected(self):
        self.write(at_utc=self.now + 10)
        with self.assertRaises(GuardExceeded):
            self.readiness()
        self.write(at_utc=self.now - 1000)
        with self.assertRaises(GuardExceeded):
            self.readiness()

    def test_durable_deadline_ignores_restarted_clock(self):
        lease.append(self.root, {"schema": lease.SCHEMA, "lease": "arm",
                                 "state": "active", "mode": "pilot",
                                 "cid": None, "cidfile": None, "pid": None,
                                 "fingerprint": None, "at_utc": 500.0})
        lease.bind_cid(self.root, "arm", "a" * 64, pid=1, fingerprint=[1, 2])
        self.assertEqual(durable_deadline(self.root, "arm", 2400), 2900.0)
        self.assertEqual(durable_deadline(self.root, "arm", 99999), 2900.0)

    def test_build_mode_fails_closed_before_spawn(self):
        with self.assertRaises(GuardExceeded) as caught:
            require_supported_mode("build")
        self.assertEqual(caught.exception.reason, "watchdog_unsupported_mode")

    def test_watchdog_teardown_downgrades_finished_receipt(self):
        watchdog.append_evidence(self.root, {
            "schema": watchdog.SCHEMA, "worker": "arm", "reason": "wall_limit",
            "result": "fail_closed", "action": "teardown"})
        state = {"status": "finished", "peak_rss": 123}
        updated = downgrade_on_watchdog_teardown(self.root, "arm", state)
        self.assertEqual(updated["status"], "failed")
        self.assertEqual(updated["reason"], "watchdog_fail_closed")
        self.assertEqual(updated["peak_rss"], 123)
        self.assertEqual(updated["watchdog_evidence"]["events"], ["wall_limit"])
        self.assertEqual(state["status"], "finished")


if __name__ == "__main__":
    unittest.main()
