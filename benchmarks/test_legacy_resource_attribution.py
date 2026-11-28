"""Exact-proof attribution of the legacy observable memory guard's SIGTERM.

All journals and logs are synthetic; the pinned guard source, resource policy
and live host journal are never read or changed by these tests.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fail_closed_guard import lease, legacy_resource, watchdog
from fail_closed_guard.watchdog_contract import downgrade_on_watchdog_teardown

sys.path.insert(0, str(Path(__file__).parent))
from assembler_bench import px_cohort_scheduler as sched  # noqa: E402
from assembler_bench.px_execution import classify  # noqa: E402

CID = "a" * 64
WORKER = "skesa-12345"
LOG_TEXT = (
    "Processing Sample S ('/reads/S_L001_R1_001.fastq.gz', "
    "'/reads/S_L001_R2_001.fastq.gz').\n"
)


class LegacyResourceAttributionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / "run.log"
        self.log.write_text(LOG_TEXT)
        self.guard = self.root / "guard.jsonl"
        self.start = 1000.0
        self.hashes = legacy_resource.command_hashes(LOG_TEXT)
        self.assertEqual(len(self.hashes), 3)

    def guard_event(self, *, digest=None, at=1005.0, resident=None,
                    action="SIGTERM"):
        event = {
            "schema": legacy_resource.SCHEMA,
            "command_sha256": digest if digest else next(iter(self.hashes)),
            "observed_utc": at,
            "rss_tree_bytes": (legacy_resource.TRIP + 1 if resident is None
                               else resident),
            "soft_trip_bytes": legacy_resource.TRIP,
            "memory_max_bytes": legacy_resource.LIMIT,
            "action": action,
        }
        with self.guard.open("a") as out:
            out.write(json.dumps(event) + "\n")
        return event

    def bind(self, *, close=True):
        lease.append(self.root, {
            "schema": lease.SCHEMA, "lease": WORKER, "owner": WORKER,
            "state": "active", "mode": "pilot", "cid": CID,
            "cidfile": None, "pid": None, "fingerprint": None,
            "at_utc": self.start})
        if close:
            lease.append(self.root, {
                "schema": lease.SCHEMA, "lease": WORKER, "owner": WORKER,
                "state": "released", "cid": CID,
                "proof": {"pilot_container_id": CID},
                "at_utc": self.start + 20})

    def probe(self, **kwargs):
        return legacy_resource.attributed_resource_stop(
            self.root, WORKER, self.log, path=self.guard, **kwargs)

    def test_exact_command_lease_and_timestamp_attributes_resource_stop(self):
        self.bind()
        self.guard_event()
        self.assertEqual(self.probe(), "observed_rss_limit")
        self.assertEqual(classify({"status": "failed",
                                   "reason": "observed_rss_limit"}),
                         "observed_rss_limit")

    def test_resource_stop_is_not_recoverable_infrastructure(self):
        self.assertNotIn("observed_rss_limit",
                         sched.INFRASTRUCTURE_FAILURE_REASONS)
        self.assertIn("observed_rss_limit", sched.FAILURE_REASONS)

    def test_wrong_command_digest_is_not_attributed(self):
        self.bind()
        self.guard_event(digest="f" * 64)
        self.assertIsNone(self.probe())

    def test_violation_outside_lease_interval_is_not_attributed(self):
        self.bind()
        self.guard_event(at=self.start - 100)
        self.assertIsNone(self.probe())

    def test_sub_trip_rss_is_not_attributed(self):
        self.bind()
        self.guard_event(resident=legacy_resource.TRIP - 1)
        self.assertIsNone(self.probe())

    def test_no_lease_binding_is_not_attributed(self):
        self.guard_event()
        self.assertIsNone(self.probe())

    def test_resource_evidence_outranks_watchdog_reason(self):
        self.bind()
        self.guard_event()
        watchdog.append_evidence(self.root, {
            "schema": watchdog.SCHEMA, "worker": WORKER,
            "reason": "binding_unavailable", "result": "fail_closed",
            "action": "teardown", "cid": CID, "lease_state": "bound",
            "durable_start": self.start, "at_utc": self.start + 1})
        state = {"status": "killed", "reason": "teardown_unverified",
                 "bound_cid": CID}
        state = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(state["reason"], "binding_unavailable")
        resource = self.probe()
        self.assertEqual(resource, "observed_rss_limit")
        # The launcher applies resource attribution after the watchdog downgrade.
        state["reason"] = resource
        self.assertEqual(classify(state), "observed_rss_limit")

    def test_pin_constants_are_unchanged(self):
        self.assertEqual(legacy_resource.LIMIT, 4_000_000_000)
        self.assertEqual(legacy_resource.TRIP, 3_700_000_000)
        self.assertEqual(sched.MAX_INFRA_ATTEMPTS, 2)
        self.assertEqual(sched.AUTHORIZED_EXTRA_ATTEMPT, 3)


if __name__ == "__main__":
    unittest.main()
