"""Evidence-bound attribution of an independent watchdog fail-closed reason.

Every probe uses an in-memory journal and synthetic identity records: no
container, lease, receipt, registry or live arm is touched. The guard against
misattribution is the subject here, not a retry or a reclassification of any
already written receipt.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from fail_closed_guard import lease, watchdog
from fail_closed_guard.watchdog_contract import downgrade_on_watchdog_teardown

sys.path.insert(0, str(Path(__file__).parent))
from assembler_bench import px_cohort_scheduler as sched  # noqa: E402
from assembler_bench.px_execution import classify  # noqa: E402

CID = "a" * 64
FOREIGN = "b" * 64
WORKER = "skesa-12345"


class WatchdogReasonAttributionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.start = 1000.0

    def bind_and_release(self, cid=CID, *, proof=True, release_at=None):
        lease.append(self.root, {
            "schema": lease.SCHEMA, "lease": WORKER, "owner": WORKER,
            "state": "active", "mode": "pilot", "cid": cid,
            "cidfile": None, "pid": None, "fingerprint": None,
            "at_utc": self.start})
        proof_value = None
        if proof is True:
            proof_value = {"pilot_container_id": cid,
                           "fresh_absence_check": True}
        elif proof == "dict_cid":
            proof_value = {"cid": cid, "container_removed": False}
        elif proof == "string":
            proof_value = cid
        lease.append(self.root, {
            "schema": lease.SCHEMA, "lease": WORKER, "owner": WORKER,
            "state": "released", "cid": cid, "proof": proof_value,
            "at_utc": self.start + 10 if release_at is None else release_at})

    def decide(self, reason="binding_unavailable", cid=CID, *, action="teardown",
               at=None, start=None, lease_state="bound"):
        event = {
            "schema": watchdog.SCHEMA, "worker": WORKER, "reason": reason,
            "result": "fail_closed", "action": action, "cid": cid,
            "cid_source": "cidfile", "lease_state": lease_state,
            "durable_start": self.start if start is None else start,
            "at_utc": self.start + 1 if at is None else at,
            "teardown": None}
        watchdog.append_evidence(self.root, event)
        return event

    # Natural assembler exit / error must keep its own classification.

    def test_natural_finish_without_watchdog_stays_success(self):
        state = {"status": "finished", "reason": None, "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["status"], "finished")
        self.assertEqual(classify(updated), "success")
        self.assertEqual(state["status"], "finished")

    def test_natural_assembler_error_stays_generic(self):
        state = {"status": "failed", "reason": "error", "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "error")
        self.assertEqual(classify(updated), "error")

    def test_launcher_owned_reason_is_never_replaced(self):
        state = {"status": "killed", "reason": "wall_limit", "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "wall_limit")
        self.assertEqual(classify(updated), "wall_limit")

    # Exact proof carries the independent reason into a FUTURE receipt.

    def test_proven_binding_unavailable_reaches_classifier(self):
        self.bind_and_release()
        self.decide("binding_unavailable")
        state = {"status": "killed", "reason": "teardown_unverified",
                 "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "binding_unavailable")
        self.assertEqual(updated["watchdog_evidence"]["attributed_reason"],
                         "binding_unavailable")
        self.assertEqual(classify(updated), "binding_unavailable")
        self.assertEqual(state["reason"], "teardown_unverified")

    def test_object_action_and_dict_teardown_proof_are_supported(self):
        self.bind_and_release(proof="dict_cid")
        self.decide("measurement_unavailable",
                    action={"action": "teardown", "cid": CID})
        state = {"status": "finished", "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["status"], "failed")
        self.assertEqual(updated["reason"], "measurement_unavailable")
        self.assertEqual(classify(updated), "measurement_unavailable")

    def test_string_proof_also_qualifies(self):
        self.bind_and_release(proof="string")
        self.decide("binding_unavailable")
        state = {"status": "failed", "reason": "error", "bound_cid": CID}
        self.assertEqual(
            downgrade_on_watchdog_teardown(self.root, WORKER, state)["reason"],
            "binding_unavailable")

    # Foreign / ambiguous CID and undecided teardown stay generic.

    def test_foreign_cid_is_not_attributed(self):
        self.bind_and_release(cid=CID)
        self.decide("binding_unavailable", cid=FOREIGN)
        state = {"status": "killed", "reason": "teardown_unverified",
                 "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "teardown_unverified")
        self.assertNotIn("attributed_reason", updated["watchdog_evidence"])
        self.assertEqual(classify(updated), "error")

    def test_foreign_cid_event_blocks_mixed_attribution(self):
        self.bind_and_release()
        self.decide("binding_unavailable", cid=CID)
        self.decide("measurement_unavailable", cid=FOREIGN)
        state = {"status": "killed", "reason": "teardown_unverified",
                 "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "teardown_unverified")

    def test_ambiguous_reasons_are_not_attributed(self):
        self.bind_and_release()
        self.decide("binding_unavailable")
        self.decide("measurement_unavailable")
        state = {"status": "finished", "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["reason"], "watchdog_fail_closed")
        self.assertEqual(classify(updated), "error")

    def test_decision_without_completed_teardown_is_generic(self):
        lease.append(self.root, {
            "schema": lease.SCHEMA, "lease": WORKER, "owner": WORKER,
            "state": "active", "mode": "pilot", "cid": CID,
            "cidfile": None, "pid": None, "fingerprint": None,
            "at_utc": self.start})
        self.decide("binding_unavailable")
        state = {"status": "finished", "bound_cid": CID}
        updated = downgrade_on_watchdog_teardown(self.root, WORKER, state)
        self.assertEqual(updated["status"], "failed")
        self.assertEqual(updated["reason"], "watchdog_fail_closed")
        self.assertNotIn("attributed_reason", updated["watchdog_evidence"])

    def test_late_decision_never_rewrites_an_existing_receipt(self):
        written = {"status": "killed", "reason": "teardown_unverified",
                   "bound_cid": CID}
        written = downgrade_on_watchdog_teardown(self.root, WORKER, written)
        self.bind_and_release()
        self.decide("binding_unavailable")
        # The already-finalized receipt is unchanged after the late decision.
        self.assertEqual(written["reason"], "teardown_unverified")
        self.assertEqual(classify(written), "error")
        # A fresh state finalized with the durable proof does attribute.
        fresh = {"status": "killed", "reason": "teardown_unverified",
                 "bound_cid": CID}
        self.assertEqual(
            downgrade_on_watchdog_teardown(self.root, WORKER, fresh)["reason"],
            "binding_unavailable")

    def test_no_broadened_retry_policy(self):
        self.assertEqual(sched.MAX_INFRA_ATTEMPTS, 2)
        self.assertEqual(sched.AUTHORIZED_EXTRA_ATTEMPT, 3)
        self.assertEqual(sched.INFRASTRUCTURE_FAILURE_REASONS,
                         frozenset(("disk_stop", "measurement_unavailable",
                                    "identity_lost", "binding_unavailable")))


if __name__ == "__main__":
    unittest.main()
