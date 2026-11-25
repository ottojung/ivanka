"""Adversarial proofs that the PX supervisor stays inert until handoff."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import exploratory_policy
from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_supervisor as sup

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"
TOOLS = ("skesa", "minia")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    return path


def cases_for(cohort, r1, r2):
    ids = [f"P{i:03d}" if cohort == "physical" else f"S{i:03d}"
           for i in range(1, sched.EXPECTED_COUNTS[cohort] + 1)]
    canonical = sched.canonical_aliases(ids, cohort)
    return [sched.CasePair(sid, canonical[sid], cohort, r1, r2) for sid in ids]


class SupervisorTests(unittest.TestCase):
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
        self.policy = patch.object(exploratory_policy, "PROVENANCE_ROOT", self.root)
        self.policy.start()
        self.addCleanup(self.policy.stop)
        # Real admission behaviour is proved in test_px_cohort_scheduler; here
        # the supervisor is exercised with a deterministic admitted decision.
        self.admission = patch("assembler_bench.exploratory_space.admit",
                               return_value={"incremental_bytes": 0,
                                             "free_bytes": 100 * 1024**3,
                                             "admitted_reservation_bytes": 1024**3})
        self.admission.start()
        self.addCleanup(self.admission.stop)

    def source(self):
        return sched.CohortSource(cases_for("physical", self.r1, self.r2),
                                  cases_for("synthetic", self.r1, self.r2))

    def registry(self, tools=TOOLS):
        data = json.loads(REGISTRY.read_text())
        promotions = {}
        for tool in tools:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            receipt = {
                "schema": "ivanka.exploratory.image.receipt.v1",
                "tool_id": tool, "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "native_binary_sha256": "a" * 64}
            path = write_json(self.root / "receipts" / (tool + ".json"), receipt)
            pilot_receipt = {
                "schema": "ivanka.exploratory.pilot.receipt.v1",
                "tool_id": tool, "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "physical": {"source_input_sha256": "c" * 64, "status": "success"},
                "synthetic": {"source_input_sha256": "d" * 64, "status": "success"}}
            pilot_path = write_json(
                self.root / "receipts" / (tool + "-pilot.json"), pilot_receipt)
            promotions[tool] = {
                "status": "pilot", "image_sha256": "b" * 64,
                "image_evidence": {"path": str(path), "sha256": sha(path)},
                "pilot_evidence": {"path": str(pilot_path),
                                   "sha256": sha(pilot_path)}}
        for tool, changes in promotions.items():
            item = next(x for x in data["candidates"] if x["id"] == tool)
            item.update(changes)
        return write_json(self.root / "registry.json", data)

    def baseline(self):
        return write_json(self.root / "baseline.json", {
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.px), "image_store": str(self.px),
            "workspace": str(self.root), "base_store_bytes": 0,
            "frozen_manifest_sha256":
                "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
            "active_job": None})

    def supervisor(self, runner, registry=None):
        def diagnostics(root, arm, case, receipt):
            sched.verify_receipt(root, arm)
            sched.write_resource(root, arm, receipt)
        return sup.BackgroundSupervisor(registry or self.registry(), self.baseline(),
                                        self.source(), self.px, runner,
                                        diagnostics=diagnostics)

    def fake_runner(self, calls, stop_after=None):
        seen = {"n": 0}

        def runner(arm, case):
            calls.append(sched.receipt_id(arm))
            seen["n"] += 1
            if stop_after is not None and seen["n"] >= stop_after:
                (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"outcome": "success", "output_path": self.out,
                    "alias": arm["alias"], "cohort": arm["cohort"],
                    "input_sha256": arm["input_sha256"],
                    "seconds": 1.0, "peak_rss": 1_000_000,
                    "runner_receipt_sha256": "c" * 64}
        return runner

    def handoff_all(self, registry):
        for tool in TOOLS:
            sup.make_handoff(self.px, registry, tool)

    def test_supervisor_cannot_start_unarmed(self):
        calls = []
        with self.assertRaisesRegex(sup.HandoffRequired, "inert"):
            self.supervisor(self.fake_runner(calls)).start()
        self.assertEqual(calls, [])

    def test_supervisor_cannot_start_without_verified_handoff(self):
        calls = []
        with self.assertRaisesRegex(sup.HandoffRequired, "handoff"):
            self.supervisor(self.fake_runner(calls)).start(armed=True)
        self.assertEqual(calls, [])

    def test_unpinned_tool_cannot_be_handed_off(self):
        data = json.loads(REGISTRY.read_text())
        registry = write_json(self.root / "raw.json", data)
        with self.assertRaisesRegex(sup.HandoffRequired, "proof"):
            sup.make_handoff(self.px, registry, "skesa")

    def test_image_receipt_alone_cannot_assert_tests_passed(self):
        registry = self.registry()
        data = json.loads(registry.read_text())
        item = next(x for x in data["candidates"] if x["id"] == "skesa")
        item.pop("pilot_evidence")
        item["status"] = "image-pinned"
        image_only = write_json(self.root / "image-only.json", data)
        with self.assertRaisesRegex(sup.HandoffRequired, "two-cohort pilot"):
            sup.make_handoff(self.px, image_only, "skesa")

    def test_tampered_handoff_never_enables_execution(self):
        calls = []
        registry = self.registry()
        self.handoff_all(registry)
        path = sup.handoff_path(self.px, "skesa")
        record = json.loads(path.read_text())
        record["agent"] = "someone-else"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(sup.HandoffRequired, "handoff"):
            self.supervisor(self.fake_runner(calls), registry).start(armed=True)
        self.assertEqual(calls, [])

    def test_resume_skips_terminal_receipts_and_balances_tools(self):
        registry = self.registry()
        self.handoff_all(registry)
        calls = []
        first = self.supervisor(self.fake_runner(calls, stop_after=2),
                                registry).start(armed=True)
        self.assertEqual(first["completed"], [
            "skesa-physical-PX-R001", "minia-physical-PX-R001"])
        self.assertEqual(first["status"], "stopped")
        (self.px / sup.STOP_FILE).unlink()
        second = self.supervisor(self.fake_runner(calls, stop_after=2),
                                 registry).start(armed=True)
        self.assertEqual(second["completed"][:2], [
            "skesa-physical-PX-R002", "minia-physical-PX-R002"])
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[:4], [
            "skesa-physical-PX-R001", "minia-physical-PX-R001",
            "skesa-physical-PX-R002", "minia-physical-PX-R002"])

    def test_balanced_dispatch_catches_up_and_preserves_plan_digest(self):
        registry = self.registry()
        plan = sched.build_plan(registry, self.source(), self.px)
        # SKESA is 120 arms ahead of Minia, like the live PX campaign.
        for arm in plan["pending"][:120]:
            self.assertEqual(arm["tool_id"], "skesa")
            sched.record_outcome(self.px, arm, self.out, "success",
                                 seconds=1.0, peak_rss=100,
                                 runner_receipt_sha256="c" * 64)
        plan = sched.build_plan(registry, self.source(), self.px)
        digest = sched._plan_digest(plan)
        pending = sched.resume(plan, self.px)
        ordered = list(sup.balanced_pending(plan, pending))
        self.assertEqual(ordered[:120],
                         [a for a in pending if a["tool_id"] == "minia"
                          and a["cohort"] == "physical"][:120])
        self.assertEqual([sched.receipt_id(a) for a in ordered[120:124]], [
            "skesa-physical-PX-R121", "minia-physical-PX-R121",
            "skesa-physical-PX-R122", "minia-physical-PX-R122"])
        self.assertEqual(len(ordered), len(pending))
        self.assertEqual({sched.receipt_id(a) for a in ordered},
                         {sched.receipt_id(a) for a in pending})
        physical = 2 * sched.PHYSICAL_COUNT - 120
        self.assertTrue(all(a["cohort"] == "physical"
                            for a in ordered[:physical]))
        self.assertTrue(all(a["cohort"] == "synthetic"
                            for a in ordered[physical:]))
        self.assertEqual(sched._plan_digest(plan), digest)

    def test_admission_stop_prevents_any_dispatch(self):
        registry = self.registry()
        self.handoff_all(registry)
        calls = []
        with (patch.object(sched, "admit_arm",
                           side_effect=ValueError("disk budget exceeded")),
              self.assertRaisesRegex(ValueError, "disk budget")):
            self.supervisor(self.fake_runner(calls), registry).start(armed=True)
        self.assertEqual(calls, [])
        self.assertEqual(list((self.px / "receipts").glob("*.json")), [])

    def test_stop_file_halts_without_touching_an_arm(self):
        registry = self.registry()
        self.handoff_all(registry)
        (self.px / sup.STOP_FILE).write_text("stop\n")
        calls = []
        result = self.supervisor(self.fake_runner(calls), registry).start(armed=True)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(calls, [])

    def test_unclassified_runner_failure_is_rejected(self):
        registry = self.registry()
        self.handoff_all(registry)
        calls = []

        def bad(arm, case):
            calls.append(1)
            return {"outcome": "failure", "failure_reason": "spurious",
                    "alias": arm["alias"], "cohort": arm["cohort"],
                    "input_sha256": arm["input_sha256"]}

        with self.assertRaisesRegex(ValueError, "not classified"):
            self.supervisor(bad, registry).start(armed=True)
        self.assertEqual(list((self.px / "receipts").glob("*.json")), [])

    def test_report_from_another_canonical_alias_is_rejected(self):
        registry = self.registry()
        self.handoff_all(registry)

        def wrong_alias(arm, case):
            return {"outcome": "success", "output_path": self.out,
                    "alias": "PX-R053", "cohort": arm["cohort"],
                    "input_sha256": arm["input_sha256"], "seconds": 1.0}

        with self.assertRaisesRegex(ValueError, "does not match dispatched case"):
            self.supervisor(wrong_alias, registry).start(armed=True)
        self.assertEqual(list((self.px / "receipts").glob("*.json")), [])

    def test_no_private_identity_reaches_receipts_or_checkpoint(self):
        registry = self.registry()
        self.handoff_all(registry)
        calls = []
        self.supervisor(self.fake_runner(calls, stop_after=1), registry).start(armed=True)
        for path in list((self.px / "receipts").glob("*.json")) + [
                sched.checkpoint_path(self.px)]:
            text = path.read_text()
            self.assertNotIn(".fastq", text)
            self.assertNotIn("secret", text)
            self.assertNotIn("/workspace", text)


if __name__ == "__main__":
    unittest.main()
