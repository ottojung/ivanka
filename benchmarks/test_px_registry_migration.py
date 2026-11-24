"""Adversarial proofs for the additive PX registry/checkpoint migration."""
import copy
import fcntl
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench import exploratory_policy
from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_registry_migration as migration
from assembler_bench import px_supervisor

TEMPLATE = (Path(__file__).resolve().parents[1]
            / "benchmarks/assembler_bench/exploratory_candidates.json")
OLD_TOOLS = ("skesa", "idba-ud")
TARGET = "ray"
WINDOW = "20261124T190000Z"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    return path


class MigrationTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        (self.root / "receipts").mkdir()
        (self.root / "handoff").mkdir()
        (self.root / "state").mkdir()
        template = json.loads(TEMPLATE.read_text())
        self.active_data = self.promoted(template, OLD_TOOLS)
        self.staged_data = self.promoted(copy.deepcopy(template),
                                         OLD_TOOLS + (TARGET,))
        self._pin_baseline()
        self.active = write_json(self.root / "active.json", self.active_data)
        self.staged = write_json(self.root / "staged.json", self.staged_data)
        self.handoff = write_json(
            self.root / "handoff" / (TARGET + ".json"), self._handoff())
        self.staged_bytes = self.staged.read_bytes()
        self.handoff_bytes = self.handoff.read_bytes()
        self.stop_token = "bounded window for " + TARGET
        (self.root / "STOP").write_text(self.stop_token + "\n")
        self.boundary = write_json(self.root / "state" / "boundary.json", {
            "window_id": WINDOW, "owner": "curtis",
            "service_stopped": True,
        })
        self.arms = [self._arm("skesa", "physical", "PX-R001"),
                     self._arm("idba-ud", "synthetic", "PX-H001")]
        self.receipt_ids = [sched.receipt_id(arm) for arm in self.arms]
        output = self.root / "conseq.csv"
        output.write_bytes(b"consensus\n")
        for arm in self.arms:
            sched.record_outcome(self.root, arm, output, "success", seconds=1)
        self.checkpoint = write_json(
            self.root / "state" / "checkpoint.json",
            {"schema": sched.CHECKPOINT_SCHEMA, "plan_sha256": "old-plan",
             "completed": [self.receipt_ids[0]]})
        self.older = write_json(
            self.root / "state" / "checkpoint-pre.json",
            {"schema": sched.CHECKPOINT_SCHEMA, "plan_sha256": "older-plan",
             "completed": [self.receipt_ids[1]]})
        self.plan = self._plan()
        self.plan_path = write_json(self.root / "migration-plan.json", self.plan)
        self.receipts_before = self._receipt_hashes()
        self.receipt_blobs = {path.name: path.read_bytes()
                              for path in (self.root / "receipts").glob("*.json")}

    def _pin_baseline(self):
        policy = self.staged_data["policy"]
        baseline = write_json(self.root / "budget-baseline.json", {
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.root),
            "image_store": policy["dedicated_image_store_root"],
            "workspace": "/workspace", "base_store_bytes": 0,
            "frozen_manifest_sha256":
                policy["frozen_seven_manifest_sha256"],
            "active_job": None,
        })
        self.active_data["storage_baseline_sha256"] = sha(baseline)
        self.staged_data["storage_baseline_sha256"] = sha(baseline)

    def _make_receipt(self, data, tool, kind, extra):
        item = next(x for x in data["candidates"] if x["id"] == tool)
        record = {
            "schema": "ivanka.exploratory." + kind + ".receipt.v1",
            "tool_id": tool, "source_commit": item["source_commit"],
            "adapter_commit": data["adapter_branch_commits"][tool],
            "image_sha256": "b" * 64, "qualifying": False,
        }
        record.update(extra)
        path = write_json(
            self.root / "receipts" / (kind + "-" + tool + ".json"), record)
        return {"path": str(path), "sha256": sha(path)}

    def promoted(self, data, tools):
        for tool in tools:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            item.update(status="pilot", image_sha256="b" * 64)
            item["image_evidence"] = self._make_receipt(
                data, tool, "image", {"native_binary_sha256": "a" * 64})
            item["pilot_evidence"] = self._make_receipt(data, tool, "pilot", {
                "physical": {"source_input_sha256": "c" * 64,
                             "status": "success"},
                "synthetic": {"source_input_sha256": "d" * 64,
                              "status": "success"},
            })
        return data

    def _handoff(self):
        item = next(x for x in self.staged_data["candidates"]
                    if x["id"] == TARGET)
        return {
            "schema": px_supervisor.HANDOFF_SCHEMA, "tool_id": TARGET,
            "board": px_supervisor.PX_BOARD, "agent": px_supervisor.IMAGE_AGENT,
            "tests_passed": True, "image_sha256": item["image_sha256"],
            "image_receipt_sha256": item["image_evidence"]["sha256"],
            "pilot_receipt_sha256": item["pilot_evidence"]["sha256"],
        }

    def _arm(self, tool, cohort, alias):
        item = next(x for x in self.staged_data["candidates"]
                    if x["id"] == tool)
        return {
            "tool_id": tool, "cohort": cohort, "alias": alias,
            "input_sha256": {"R1": "e" * 64, "R2": "f" * 64},
            "source_commit": item["source_commit"],
            "adapter_commit": self.staged_data["adapter_branch_commits"][tool],
            "image_sha256": item["image_sha256"],
        }

    def _case_input_hashes(self):
        hashes = {}
        for cohort, count, prefix in (
                ("physical", sched.PHYSICAL_COUNT, "R"),
                ("synthetic", sched.SYNTHETIC_COUNT, "H")):
            for i in range(1, count + 1):
                hashes[f"{cohort},PX-{prefix}{i:03d}"] = {
                    "R1": "e" * 64, "R2": "f" * 64}
        return hashes

    def _plan(self):
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        item = next(x for x in data["candidates"] if x["id"] == TARGET)
        case_hashes = self._case_input_hashes()
        digest_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                         for k, v in case_hashes.items()}
        return {
            "schema": migration.PLAN_SCHEMA, "window_id": WINDOW,
            "tool_id": TARGET, "active_registry": "active.json",
            "staged_registry": "staged.json",
            "staged_registry_sha256": sha(self.staged),
            "source_commit": item["source_commit"],
            "image_sha256": item["image_sha256"],
            "image_receipt_sha256": item["image_evidence"]["sha256"],
            "pilot_receipt_sha256": item["pilot_evidence"]["sha256"],
            "handoff_sha256": sha(self.handoff),
            "new_plan_sha256": migration.expected_plan_digest(
                self.staged, data, case_input_hashes=digest_hashes),
            "active_checkpoint": "state/checkpoint.json",
            "checkpoints": ["state/checkpoint.json", "state/checkpoint-pre.json"],
            "new_completed": [], "stop_token": self.stop_token,
            "owner": "curtis",
            "boundary_evidence": {
                "kind": "stopped-service-or-owner",
                "path": "state/boundary.json",
            },
            "case_input_hashes": case_hashes,
        }

    def _receipt_hashes(self):
        return {path.name: sha(path)
                for path in (self.root / "receipts").glob("*.json")}

    def _refresh_plan(self):
        self.plan_path = write_json(self.root / "migration-plan.json", self.plan)

    def test_additive_migration_preserves_receipts_and_checkpoints(self):
        result = migration.apply(self.root, self.plan_path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual((self.root / "active.json").read_bytes(),
                         self.staged.read_bytes())
        checkpoint = json.loads(self.checkpoint.read_text())
        self.assertEqual(checkpoint["plan_sha256"], self.plan["new_plan_sha256"])
        self.assertEqual(checkpoint["completed"], sorted(self.receipt_ids))
        preserved = self.root / "preserved" / WINDOW
        for name, source in (("active.json", self.staged),
                             ("state/checkpoint.json", self.checkpoint),
                             ("state/checkpoint-pre.json", self.older)):
            self.assertTrue((preserved / name).is_file(), name)
        receipt = json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(receipt["schema"], migration.RECEIPT_SCHEMA)
        self.assertEqual(receipt["tool_id"], TARGET)
        self.assertEqual(
            receipt["accepted_arms_derived_from_scheduler_receipts"], 2)
        self.assertFalse(receipt["pilot_arms_marked_complete"])
        self.assertEqual(receipt["new_completed"], [])
        self.assertEqual(receipt["before"]["active_registry_sha256"],
                         sha(preserved / "active.json"))
        self.assertEqual(receipt["after"]["checkpoint_sha256"],
                         sha(self.checkpoint))
        after = self._receipt_hashes()
        for name, digest in self.receipts_before.items():
            self.assertEqual(after[name], digest)

    def test_second_apply_is_idempotent(self):
        first = migration.apply(self.root, self.plan_path)
        second = migration.apply(self.root, self.plan_path)
        self.assertEqual(second["status"], "already-applied")
        self.assertEqual(second["receipt"], first["receipt"])
        after = self._receipt_hashes()
        self.assertEqual(len(after), len(self.receipts_before) + 1)
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         sorted(self.receipt_ids))

    def test_recovers_checkpoint_after_interrupted_swap(self):
        (self.root / "active.json").write_bytes(self.staged.read_bytes())
        result = migration.apply(self.root, self.plan_path)
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(json.loads(self.checkpoint.read_text())["plan_sha256"],
                         self.plan["new_plan_sha256"])
        self.assertTrue(Path(result["receipt"]).is_file())

    def _refresh_for_staged(self, staged_data):
        write_json(self.staged, staged_data)
        self.staged_bytes = self.staged.read_bytes()
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        case_hashes = self._case_input_hashes()
        digest_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                         for k, v in case_hashes.items()}
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["new_plan_sha256"] = migration.expected_plan_digest(
            self.staged, data, case_input_hashes=digest_hashes)
        self.plan["case_input_hashes"] = case_hashes
        self._refresh_plan()

    def test_rejects_change_or_removal_of_existing_arm_identity(self):
        changed = copy.deepcopy(self.staged_data)
        next(x for x in changed["candidates"] if x["id"] == "skesa")[
            "source_commit"] = "3" * 40
        write_json(self.staged, changed)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["case_input_hashes"] = self._case_input_hashes()
        # Digest recomputed from raw data; checked() will fail before apply.
        digest_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                         for k, v in self.plan["case_input_hashes"].items()}
        self.plan["new_plan_sha256"] = migration.expected_plan_digest(
            self.staged, changed, case_input_hashes=digest_hashes)
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "registry policy|previously eligible identity changed"):
            migration.apply(self.root, self.plan_path)

        removed = copy.deepcopy(self.staged_data)
        removed["candidates"] = [x for x in removed["candidates"]
                                 if x["id"] != "skesa"]
        write_json(self.staged, removed)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        digest_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                         for k, v in self._case_input_hashes().items()}
        self.plan["case_input_hashes"] = self._case_input_hashes()
        self.plan["new_plan_sha256"] = migration.expected_plan_digest(
            self.staged, removed, case_input_hashes=digest_hashes)
        self._refresh_plan()
        with self.assertRaises(migration.MigrationError):
            migration.apply(self.root, self.plan_path)

    def test_rejects_corrupt_and_unreceipted_completed_arms(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        receipt.write_text(receipt.read_text().replace('"success"', '"failure"'))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt"):
            migration.apply(self.root, self.plan_path)
        receipt.write_bytes(self.receipt_blobs[receipt.name])

    def test_rejects_pilot_alias_marked_complete_without_scheduler_receipt(self):
        self.plan["new_completed"] = ["ray-physical-PX-R001"]
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "no scheduler receipt"):
            migration.apply(self.root, self.plan_path)
        self.assertFalse((self.root / "receipts" / (
            "registry-migration-" + TARGET + "-" + WINDOW + ".json")).exists())

    def test_rejects_held_worker_lock(self):
        lock = (self.root / ".global-worker.lock").open("a+")
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(lambda: fcntl.flock(lock, fcntl.LOCK_UN))
        with self.assertRaisesRegex(migration.MigrationError, "lock is held"):
            migration.apply(self.root, self.plan_path)

    def test_rejects_missing_stop_or_active_arm(self):
        (self.root / "STOP").unlink()
        with self.assertRaisesRegex(migration.MigrationError, "STOP"):
            migration.apply(self.root, self.plan_path)
        (self.root / "STOP").write_text(self.stop_token + "\n")
        baseline_path = self.root / "budget-baseline.json"
        baseline = json.loads(baseline_path.read_text())
        baseline["active_job"] = "live-arm"
        write_json(baseline_path, baseline)
        with self.assertRaisesRegex(migration.MigrationError, "active arm"):
            migration.apply(self.root, self.plan_path)

    def test_rejects_staged_registry_handoff_and_plan_drift(self):
        self.staged.write_text(self.staged.read_text() + " ")
        with self.assertRaisesRegex(migration.MigrationError,
                                    "staged registry drift"):
            migration.apply(self.root, self.plan_path)
        self.staged.write_bytes(self.staged_bytes)
        self.handoff.write_text(self.handoff.read_text() + " ")
        with self.assertRaisesRegex(migration.MigrationError, "handoff drift"):
            migration.apply(self.root, self.plan_path)
        self.handoff.write_bytes(self.handoff_bytes)
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError, "plan digest drift"):
            migration.apply(self.root, self.plan_path)

    def test_rejects_plan_that_changes_the_source_or_proof_pins(self):
        self.plan["source_commit"] = "4" * 40
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "source pin differs"):
            migration.apply(self.root, self.plan_path)
        self.plan["source_commit"] = next(
            x for x in self.staged_data["candidates"]
            if x["id"] == TARGET)["source_commit"]
        self.plan["image_receipt_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "receipt hash differs from plan"):
            migration.apply(self.root, self.plan_path)

    def test_image_pinned_to_pilot_promotion_is_allowed(self):
        template = json.loads(TEMPLATE.read_text())
        active = self.promoted(template, OLD_TOOLS)
        staged = self.promoted(copy.deepcopy(template), OLD_TOOLS)
        # Promote skesa from image-pinned to pilot in staged.
        skesa = next(x for x in staged["candidates"] if x["id"] == "skesa")
        skesa["status"] = "pilot"
        skesa["image_sha256"] = "b" * 64
        skesa_active = next(x for x in active["candidates"] if x["id"] == "skesa")
        skesa_active["status"] = "image-pinned"
        skesa_active["image_sha256"] = "b" * 64
        skesa_active.pop("pilot_evidence", None)
        self.active_data = active
        self.staged_data = staged
        self._pin_baseline()
        write_json(self.active, self.active_data)
        write_json(self.staged, self.staged_data)
        self.handoff = write_json(self.root / "handoff/skesa.json", {
            "schema": px_supervisor.HANDOFF_SCHEMA, "tool_id": "skesa",
            "board": px_supervisor.PX_BOARD, "agent": px_supervisor.IMAGE_AGENT,
            "tests_passed": True, "image_sha256": skesa["image_sha256"],
            "image_receipt_sha256": skesa["image_evidence"]["sha256"],
            "pilot_receipt_sha256": skesa["pilot_evidence"]["sha256"],
        })
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        case_hashes = self._case_input_hashes()
        digest_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                         for k, v in case_hashes.items()}
        self.plan = {
            "schema": migration.PLAN_SCHEMA, "window_id": WINDOW,
            "tool_id": "skesa", "active_registry": "active.json",
            "staged_registry": "staged.json",
            "staged_registry_sha256": sha(self.staged),
            "source_commit": skesa["source_commit"],
            "image_sha256": skesa["image_sha256"],
            "image_receipt_sha256": skesa["image_evidence"]["sha256"],
            "pilot_receipt_sha256": skesa["pilot_evidence"]["sha256"],
            "handoff_sha256": sha(self.handoff),
            "new_plan_sha256": migration.expected_plan_digest(
                self.staged, data, case_input_hashes=digest_hashes),
            "active_checkpoint": "state/checkpoint.json",
            "checkpoints": ["state/checkpoint.json", "state/checkpoint-pre.json"],
            "new_completed": [], "stop_token": self.stop_token,
            "owner": "curtis",
            "boundary_evidence": {
                "kind": "stopped-service-or-owner",
                "path": "state/boundary.json",
            },
            "case_input_hashes": case_hashes,
        }
        self._refresh_plan()
        result = migration.apply(self.root, self.plan_path)
        self.assertEqual(result["status"], "applied")

    def test_noneligible_adapter_pin_change_is_allowed(self):
        changed = copy.deepcopy(self.staged_data)
        target = next(x for x in changed["candidates"] if x["id"] == "ray")
        target["status"] = "image-pinned"
        changed["adapter_branch_commits"]["minia"] = "4" * 40
        self._refresh_for_staged(changed)
        result = migration.apply(self.root, self.plan_path)
        self.assertEqual(result["status"], "applied")

    def test_retryable_infra_failure_not_counted_as_terminal(self):
        arm = self._arm(TARGET, "physical", "PX-R002")
        sched.record_outcome(self.root, arm, None, "failure",
                             failure_reason="disk_stop")
        self.plan["new_completed"] = [sched.receipt_id(arm)]
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "not terminal-accepted"):
            migration.apply(self.root, self.plan_path)

    def test_receipt_identity_and_input_hash_validation(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        raw = json.loads(receipt.read_text())
        raw["input_sha256"]["R1"] = "z" * 64
        receipt.write_text(json.dumps(raw))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt|input hashes invalid|identity drift"):
            migration.apply(self.root, self.plan_path)

    def test_recovery_after_checkpoint_swap_before_receipt(self):
        # Simulate checkpoint swap without receipt: write target checkpoint.
        completed = sorted(self.receipt_ids)
        target_cp = {"schema": sched.CHECKPOINT_SCHEMA,
                     "plan_sha256": self.plan["new_plan_sha256"],
                     "completed": completed}
        write_json(self.checkpoint, target_cp)
        result = migration.apply(self.root, self.plan_path)
        self.assertIn(result["status"], ("applied", "recovered"))
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         completed)
        self.assertTrue(Path(result["receipt"]).is_file())

    def test_root_relative_plan_path_digest(self):
        plan_path = Path("migration-plan.json")
        result = migration.apply(self.root, plan_path)
        self.assertEqual(result["status"], "applied")

    def test_boundary_requires_stopped_service_or_owner(self):
        self.boundary.write_text(json.dumps({
            "window_id": WINDOW, "owner": "someone-else",
            "service_stopped": True}))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "boundary evidence"):
            migration.apply(self.root, self.plan_path)

    def test_digest_changes_when_stable_arm_identity_changes(self):
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        case_hashes = {(k.split(",", 1)[0], k.split(",", 1)[1]): v
                       for k, v in self._case_input_hashes().items()}
        digest = migration.expected_plan_digest(
            self.staged, data, case_input_hashes=case_hashes)
        changed = copy.deepcopy(self.staged_data)
        next(x for x in changed["candidates"] if x["id"] == TARGET)[
            "image_sha256"] = "c" * 64
        changed_path = write_json(self.root / "changed.json", changed)
        digest2 = migration.expected_plan_digest(
            changed_path, changed, case_input_hashes=case_hashes)
        self.assertNotEqual(digest, digest2)

    def test_rejects_receipt_alias_and_identity_drift(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        raw = json.loads(receipt.read_text())
        raw["alias"] = "PX-R999"
        receipt.write_text(json.dumps(raw))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt|receipt not in staged plan|alias invalid|no scheduler receipt"):
            migration.apply(self.root, self.plan_path)


if __name__ == "__main__":
    unittest.main()
