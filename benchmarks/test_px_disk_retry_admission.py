"""Adversarial proofs that a disk_stop retry never spends its attempt at low headroom."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_disk_retry_admission as admission
from assembler_bench import px_retry_authorization as authz
from assembler_bench import px_supervisor as sup
from test_px_supervisor import REGISTRY, TOOLS, cases_for, sha, write_json


class DiskRetryAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.px = self.root / "px"
        self.px.mkdir()
        self.r1 = self.root / "secret-R1.fastq.gz"
        self.r2 = self.root / "secret-R2.fastq.gz"
        self.r1.write_bytes(b"@secret\nACGT\n+\n!!!!\n")
        self.r2.write_bytes(b"@secret\nTGCA\n+\n!!!!\n")
        self.out = self.root / "conseq.csv"
        self.out.write_bytes(b"consensus\n")
        provenance = patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                           self.root)
        provenance.start()
        self.addCleanup(provenance.stop)

        def space_gate(registry, baseline, root, image_store, workspace, proposed):
            if proposed > 1024**3:
                raise ValueError("exploration would breach the workspace reserve")
            return {"free_bytes": 100 * 1024**3,
                    "admitted_reservation_bytes": proposed}

        gate = patch("assembler_bench.exploratory_space.admit_reserve",
                     side_effect=space_gate)
        gate.start()
        self.addCleanup(gate.stop)
        # These proofs need one deterministic arm, not the whole 662-case plan.
        single = patch.object(sup, "balanced_pending",
                              side_effect=lambda plan, pending: iter(
                                  [pending[0]] if pending else []))
        single.start()
        self.addCleanup(single.stop)
        data = json.loads(REGISTRY.read_text())
        for tool in TOOLS:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            adapter = data["adapter_branch_commits"][tool]
            image_path = write_json(
                self.root / "receipts" / (tool + ".json"), {
                    "schema": "ivanka.exploratory.image.receipt.v1",
                    "tool_id": tool, "source_commit": item["source_commit"],
                    "adapter_commit": adapter, "image_sha256": "b" * 64,
                    "qualifying": False, "native_binary_sha256": "a" * 64})
            pilot_path = write_json(
                self.root / "receipts" / (tool + "-pilot.json"), {
                    "schema": "ivanka.exploratory.pilot.receipt.v1",
                    "tool_id": tool, "source_commit": item["source_commit"],
                    "adapter_commit": adapter, "image_sha256": "b" * 64,
                    "qualifying": False,
                    "physical": {"source_input_sha256": "c" * 64,
                                 "status": "success"},
                    "synthetic": {"source_input_sha256": "d" * 64,
                                  "status": "success"}})
            item.update(status="pilot", image_sha256="b" * 64,
                        image_evidence={"path": str(image_path),
                                        "sha256": sha(image_path)},
                        pilot_evidence={"path": str(pilot_path),
                                        "sha256": sha(pilot_path)})
        self.registry = write_json(self.root / "registry.json", data)
        self.baseline = write_json(self.root / "baseline.json", {
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.px), "image_store": str(self.px),
            "workspace": str(self.root), "base_store_bytes": 0,
            "frozen_manifest_sha256":
                "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
            "active_job": None})
        self.source = sched.CohortSource(
            cases_for("physical", self.r1, self.r2),
            cases_for("synthetic", self.r1, self.r2))
        for tool in TOOLS:
            sup.make_handoff(self.px, self.registry, tool)

    def supervisor(self, runner):
        return sup.BackgroundSupervisor(
            self.registry, self.baseline, self.source, self.px, runner,
            diagnostics=lambda root, arm, case, receipt: None)

    def first_arm(self):
        return sched.build_plan(self.registry, self.source, self.px)["pending"][0]

    def disk_failure(self, calls):
        def runner(case_arm, case):
            calls.append(case_arm["alias"])
            return {"outcome": "failure", "failure_reason": "disk_stop",
                    "alias": case_arm["alias"], "cohort": case_arm["cohort"],
                    "input_sha256": case_arm["input_sha256"]}
        return runner

    def test_reservation_is_strictly_larger_and_bounded(self):
        self.assertEqual(admission.proposed_reservation(1024**3), 2 * 1024**3)
        self.assertEqual(admission.proposed_reservation(3 * 1024**3, 1024**3),
                         4 * 1024**3)
        for reserve, extra in ((0, 1), (1024**3, 0), (3 * 1024**3, 2 * 1024**3),
                               (1024**3, 4 * 1024**3), (True, 1)):
            with self.assertRaises(ValueError):
                admission.proposed_reservation(reserve, extra)

    def test_evaluate_defers_and_records_measured_headroom(self):
        decision = admission.evaluate(self.registry, self.baseline, self.px,
                                      1024**3,
                                      available=lambda _: 30 * 1024**3)
        self.assertEqual(decision["action"], "defer")
        self.assertEqual(decision["proposed_reservation_bytes"], 2 * 1024**3)
        self.assertEqual(decision["free_bytes"], 30 * 1024**3)
        self.assertIn("workspace reserve", decision["reason"])

    def test_evaluate_admits_with_verified_extra_headroom(self):
        with patch("assembler_bench.exploratory_space.admit_reserve",
                   return_value={"free_bytes": 40 * 1024**3,
                                 "admitted_reservation_bytes": 2 * 1024**3}):
            decision = admission.evaluate(self.registry, self.baseline, self.px,
                                          1024**3)
        self.assertEqual(decision["action"], "retry")
        self.assertEqual(decision["free_bytes"], 40 * 1024**3)

    def test_deferred_record_is_immutable_and_arm_scoped(self):
        arm = self.first_arm()
        receipt = sched.record_outcome(self.px, arm, None, "failure",
                                       failure_reason="disk_stop")
        decision = {"schema": admission.ADMISSION_SCHEMA, "action": "defer",
                    "proposed_reservation_bytes": 2 * 1024**3,
                    "reason": "workspace reserve"}
        path = admission.record_deferred(self.px, arm, decision, prior=receipt)
        self.assertEqual(path, admission.deferred_path(self.px, arm))
        self.assertEqual(admission.record_deferred(self.px, arm, decision,
                                                   prior=receipt), path)
        changed = dict(decision, reason="different")
        with self.assertRaisesRegex(ValueError, "deferred PX state changed"):
            admission.record_deferred(self.px, arm, changed, prior=receipt)
        with self.assertRaisesRegex(ValueError, "only a disk_stop"):
            admission.record_deferred(self.px, arm, decision,
                                      prior=dict(receipt, failure_reason="error"))

    def test_disk_stop_retry_defers_without_second_attempt(self):
        arm = self.first_arm()
        calls = []
        result = self.supervisor(self.disk_failure(calls)).start(armed=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["deferred"], [sched.receipt_id(arm)])
        self.assertEqual(result["completed"], [])
        receipt = sched.verify_receipt(self.px, arm)
        self.assertEqual(receipt["attempt"], 1)
        self.assertEqual(receipt["failure_reason"], "disk_stop")
        path = admission.deferred_path(self.px, arm)
        self.assertTrue(path.is_file())
        record = json.loads(path.read_bytes())
        self.assertEqual(record["schema"], admission.SCHEMA)
        self.assertEqual(record["decision"]["action"], "defer")
        self.assertFalse(authz.authorization_path(self.px, arm).exists())

    def test_authorized_extra_attempt_is_not_claimed_when_deferred(self):
        arm = self.first_arm()
        sched.record_outcome(self.px, arm, None, "failure",
                             failure_reason="disk_stop")
        sched.record_outcome(self.px, arm, None, "failure",
                             failure_reason="disk_stop")
        from assembler_bench import px_guard_source as guard_source
        with patch.object(guard_source, "verify",
                          return_value={guard_source.RESERVE_SOURCE: "a" * 64}):
            authz.authorize(self.px, arm)
            calls = []
            with patch.object(authz, "claim") as claim:
                result = self.supervisor(self.disk_failure(calls)).start(
                    armed=True)
            claim.assert_not_called()
        self.assertEqual(calls, [])
        self.assertEqual(result["completed"], [])
        self.assertEqual(result["deferred"], [sched.receipt_id(arm)])
        self.assertFalse(authz.dispatch_path(self.px, arm).exists())
        self.assertEqual(sched.verify_receipt(self.px, arm)["attempt"], 2)

    def test_retry_proceeds_only_with_extra_verified_headroom(self):
        arm = self.first_arm()
        calls = []

        def runner(case_arm, case):
            calls.append(case_arm["alias"])
            if len(calls) == 1:
                return {"outcome": "failure", "failure_reason": "disk_stop",
                        "alias": case_arm["alias"], "cohort": case_arm["cohort"],
                        "input_sha256": case_arm["input_sha256"]}
            return {"outcome": "success", "output_path": self.out,
                    "alias": case_arm["alias"], "cohort": case_arm["cohort"],
                    "input_sha256": case_arm["input_sha256"],
                    "seconds": 1.0, "peak_rss": 1_000_000,
                    "runner_receipt_sha256": "c" * 64}

        with patch("assembler_bench.exploratory_space.admit_reserve",
                   return_value={"free_bytes": 40 * 1024**3,
                                 "admitted_reservation_bytes": 2 * 1024**3}):
            result = self.supervisor(runner).start(armed=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["deferred"], [])
        self.assertEqual(sched.verify_receipt(self.px, arm)["attempt"], 2)
        self.assertFalse(admission.deferred_path(self.px, arm).exists())


if __name__ == "__main__":
    unittest.main()
