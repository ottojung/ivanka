"""Adversarial proofs for the additive PX registry/checkpoint migration."""
import copy
import fcntl
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def _source(self, hashes=None):
        return migration.InjectedCaseSource(hashes or self._case_input_hashes())

    def _expected_digest(self, staged=None, hashes=None):
        return migration.expected_plan_digest(
            self.root, staged or self.staged, self._source(hashes),
            provenance_root=self.root / "receipts")

    def _apply(self, plan_path=None, source=None):
        # Tests inject an explicit source; production apply hashes the real
        # frozen cohort through px_execution.load_cohort().
        return migration.apply(
            self.root, plan_path or self.plan_path,
            source=source if source is not None else self._source())

    def _interrupted_apply(self, crash_on):
        """Crash immediately after a real journaled write, leaving partial state."""
        real_write = sched._atomic_write

        def crash(path, data):
            result = real_write(path, data)
            if Path(path) == crash_on:
                raise OSError("simulated interruption after " + str(path))
            return result

        with mock.patch.object(sched, "_atomic_write", side_effect=crash):
            with self.assertRaises(OSError):
                self._apply()

    def _plan(self):
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        item = next(x for x in data["candidates"] if x["id"] == TARGET)
        case_hashes = self._case_input_hashes()
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
            "new_plan_sha256": self._expected_digest(),
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
        result = self._apply()
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
        first = self._apply()
        second = self._apply()
        self.assertEqual(second["status"], "already-applied")
        self.assertEqual(second["receipt"], first["receipt"])
        after = self._receipt_hashes()
        self.assertEqual(len(after), len(self.receipts_before) + 1)
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         sorted(self.receipt_ids))

    def test_recovers_checkpoint_after_interrupted_swap(self):
        self._interrupted_apply(self.active)
        result = self._apply()
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(json.loads(self.checkpoint.read_text())["plan_sha256"],
                         self.plan["new_plan_sha256"])
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         sorted(self.receipt_ids))
        self.assertTrue(Path(result["receipt"]).is_file())
        self.assertFalse(migration._journal_path(self.root, self.plan).exists())

    def _refresh_for_staged(self, staged_data):
        write_json(self.staged, staged_data)
        self.staged_bytes = self.staged.read_bytes()
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["new_plan_sha256"] = self._expected_digest()
        self.plan["case_input_hashes"] = self._case_input_hashes()
        self._refresh_plan()

    def test_rejects_change_or_removal_of_existing_arm_identity(self):
        changed = copy.deepcopy(self.staged_data)
        next(x for x in changed["candidates"] if x["id"] == "skesa")[
            "source_commit"] = "3" * 40
        write_json(self.staged, changed)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["case_input_hashes"] = self._case_input_hashes()
        # The staged registry is deliberately uncheckable; proof verification
        # must fail before any digest comparison.
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "registry policy|previously eligible identity changed"):
            self._apply()

        removed = copy.deepcopy(self.staged_data)
        removed["candidates"] = [x for x in removed["candidates"]
                                 if x["id"] != "skesa"]
        write_json(self.staged, removed)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["case_input_hashes"] = self._case_input_hashes()
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaises(migration.MigrationError):
            self._apply()

    def test_rejects_corrupt_and_unreceipted_completed_arms(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        receipt.write_text(receipt.read_text().replace('"success"', '"failure"'))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt"):
            self._apply()
        receipt.write_bytes(self.receipt_blobs[receipt.name])

    def test_rejects_pilot_alias_marked_complete_without_scheduler_receipt(self):
        self.plan["new_completed"] = ["ray-physical-PX-R001"]
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "no scheduler receipt"):
            self._apply()
        self.assertFalse((self.root / "receipts" / (
            "registry-migration-" + TARGET + "-" + WINDOW + ".json")).exists())

    def test_rejects_held_worker_lock(self):
        lock = (self.root / ".global-worker.lock").open("a+")
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(lambda: fcntl.flock(lock, fcntl.LOCK_UN))
        with self.assertRaisesRegex(migration.MigrationError, "lock is held"):
            self._apply()

    def test_rejects_missing_stop_or_active_arm(self):
        (self.root / "STOP").unlink()
        with self.assertRaisesRegex(migration.MigrationError, "STOP"):
            self._apply()
        (self.root / "STOP").write_text(self.stop_token + "\n")
        baseline_path = self.root / "budget-baseline.json"
        baseline = json.loads(baseline_path.read_text())
        baseline["active_job"] = "live-arm"
        write_json(baseline_path, baseline)
        with self.assertRaisesRegex(migration.MigrationError, "active arm"):
            self._apply()

    def test_rejects_staged_registry_handoff_and_plan_drift(self):
        self.staged.write_text(self.staged.read_text() + " ")
        with self.assertRaisesRegex(migration.MigrationError,
                                    "staged registry drift"):
            self._apply()
        self.staged.write_bytes(self.staged_bytes)
        self.handoff.write_text(self.handoff.read_text() + " ")
        with self.assertRaisesRegex(migration.MigrationError, "handoff drift"):
            self._apply()
        self.handoff.write_bytes(self.handoff_bytes)
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError, "plan digest drift"):
            self._apply()

    def test_rejects_plan_that_changes_the_source_or_proof_pins(self):
        self.plan["source_commit"] = "4" * 40
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "source pin differs"):
            self._apply()
        self.plan["source_commit"] = next(
            x for x in self.staged_data["candidates"]
            if x["id"] == TARGET)["source_commit"]
        self.plan["image_receipt_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "receipt hash differs from plan"):
            self._apply()

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
        case_hashes = self._case_input_hashes()
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
            "new_plan_sha256": self._expected_digest(),
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
        result = self._apply()
        self.assertEqual(result["status"], "applied")

    def test_nonadmitted_adapter_pin_change_is_allowed(self):
        changed = copy.deepcopy(self.staged_data)
        # Ray stays the admitted target; a non-admitted tool may move its pin.
        changed["adapter_branch_commits"]["unicycler"] = "4" * 40
        self._refresh_for_staged(changed)
        result = self._apply()
        self.assertEqual(result["status"], "applied")

    def test_retryable_infra_failure_not_counted_as_terminal(self):
        arm = self._arm(TARGET, "physical", "PX-R002")
        sched.record_outcome(self.root, arm, None, "failure",
                             failure_reason="disk_stop")
        self.plan["new_completed"] = [sched.receipt_id(arm)]
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "not terminal-accepted"):
            self._apply()

    def test_exhausted_disk_stop_receipt_is_terminal_accepted(self):
        arm = self._arm(TARGET, "physical", "PX-R002")
        # attempt 1: retryable infra failure
        sched.record_outcome(self.root, arm, None, "failure",
                             failure_reason="disk_stop")
        # attempt 2: exhausted - terminal-accepted for migration accounting
        sched.record_outcome(self.root, arm, None, "failure",
                             failure_reason="disk_stop")
        self.plan["new_completed"] = [sched.receipt_id(arm)]
        self._refresh_plan()
        result = self._apply()
        self.assertIn(result["status"], ("applied", "recovered"))

    def test_receipt_identity_and_input_hash_validation(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        raw = json.loads(receipt.read_text())
        raw["input_sha256"]["R1"] = "z" * 64
        receipt.write_text(json.dumps(raw))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt|input hashes invalid|identity drift"):
            self._apply()

    def test_recovery_after_checkpoint_swap_before_receipt(self):
        # Real journaled interruption after the checkpoint swap, no receipt.
        self._interrupted_apply(self.checkpoint)
        completed = sorted(self.receipt_ids)
        result = self._apply()
        self.assertIn(result["status"], ("applied", "recovered"))
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         completed)
        self.assertTrue(Path(result["receipt"]).is_file())

    def test_root_relative_plan_path_digest(self):
        plan_path = Path("migration-plan.json")
        result = self._apply(plan_path)
        self.assertEqual(result["status"], "applied")

    def test_boundary_requires_stopped_service_or_owner(self):
        self.boundary.write_text(json.dumps({
            "window_id": WINDOW, "owner": "someone-else",
            "service_stopped": True}))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "boundary evidence"):
            self._apply()

    def test_digest_changes_when_stable_arm_identity_changes(self):
        case_hashes = self._case_input_hashes()
        digest = self._expected_digest(hashes=case_hashes)
        changed = copy.deepcopy(self.staged_data)
        changed["policy"]["frozen_seven_manifest_sha256"] = "c" * 64
        changed_path = write_json(self.root / "changed.json", changed)
        digest2 = self._expected_digest(changed_path, hashes=case_hashes)
        self.assertNotEqual(digest, digest2)

    def test_rejects_receipt_alias_and_identity_drift(self):
        receipt = self.root / "receipts" / (self.receipt_ids[0] + ".json")
        raw = json.loads(receipt.read_text())
        raw["alias"] = "PX-R999"
        receipt.write_text(json.dumps(raw))
        with self.assertRaisesRegex(migration.MigrationError,
                                    "corrupt scheduler receipt|receipt not in staged plan|alias invalid|no scheduler receipt"):
            self._apply()

    # --- planner reuse, sparse coverage and admission rules -----------------

    def _evidence(self, data, tool, kind, image, *, status="success", suffix=""):
        item = next(x for x in data["candidates"] if x["id"] == tool)
        record = {
            "schema": "ivanka.exploratory." + kind + ".receipt.v1",
            "tool_id": tool, "source_commit": item["source_commit"],
            "adapter_commit": data["adapter_branch_commits"][tool],
            "image_sha256": image, "qualifying": False,
        }
        if kind == "image":
            record["native_binary_sha256"] = "a" * 64
        else:
            for cohort in ("physical", "synthetic"):
                record[cohort] = {"source_input_sha256": "c" * 64,
                                  "status": status}
        path = write_json(self.root / "receipts" / (
            kind + "-" + tool + suffix + ".json"), record)
        return {"path": str(path), "sha256": sha(path)}

    def test_real_planner_digest_with_sparse_accepted_receipts(self):
        source = self._source()
        built = sched.build_plan(self.staged, source, self.root,
                                 provenance_root=self.root / "receipts")
        self.assertEqual(self.plan["new_plan_sha256"], sched._plan_digest(built))
        self.assertEqual(built["total_arms"], 3 * 662)
        self.assertEqual(built["accepted_arms"], 2)
        # The scheduler is tool-major within each cohort: the second tool starts
        # again at R001 instead of continuing where the first tool stopped.
        identities = built["arm_identities"]
        self.assertEqual(identities[0]["alias"], "PX-R001")
        self.assertEqual(identities[197]["alias"], "PX-R198")
        self.assertEqual([a["tool_id"] for a in identities[:198]],
                         [identities[0]["tool_id"]] * 198)
        self.assertEqual(identities[198]["alias"], "PX-R001")
        self.assertNotEqual(identities[198]["tool_id"], identities[0]["tool_id"])
        result = self._apply()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(json.loads(self.checkpoint.read_text())["completed"],
                         sorted(self.receipt_ids))

    def test_sparse_plan_case_hashes_are_rejected(self):
        hashes = self._case_input_hashes()
        del hashes["physical,PX-R198"]
        with self.assertRaisesRegex(migration.MigrationError, "incomplete"):
            migration.InjectedCaseSource(hashes)
        hashes = self._case_input_hashes()
        hashes["physical,PX-R999"] = {"R1": "e" * 64, "R2": "f" * 64}
        with self.assertRaisesRegex(migration.MigrationError, "unknown case"):
            migration.InjectedCaseSource(hashes)

    def test_production_apply_hashes_real_source_by_default(self):
        with mock.patch.object(migration.px_execution, "load_cohort",
                               return_value=self._source()):
            result = migration.apply(self.root, self.plan_path)
        self.assertEqual(result["status"], "applied")

    def test_production_apply_refutes_forged_pending_hash(self):
        hashes = self._case_input_hashes()
        hashes["physical,PX-R198"] = {"R1": "0" * 64, "R2": "f" * 64}
        self.plan["case_input_hashes"] = hashes
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with mock.patch.object(migration.px_execution, "load_cohort",
                               return_value=self._source()):
            with self.assertRaisesRegex(migration.MigrationError,
                                        "case hash is not source-attested"):
                migration.apply(self.root, self.plan_path)

    def test_forged_pending_case_hash_is_rejected(self):
        # R198 is pending: no receipt attests it, so only hashing the real
        # source can refute a forged digest for this case.
        hashes = self._case_input_hashes()
        hashes["physical,PX-R198"] = {"R1": "0" * 64, "R2": "f" * 64}
        self.plan["case_input_hashes"] = hashes
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "case hash is not source-attested"):
            self._apply()
        self.assertFalse((self.root / "receipts" / (
            "registry-migration-" + TARGET + "-" + WINDOW + ".json")).exists())

    def test_case_hash_keys_must_be_exactly_r1_and_r2(self):
        hashes = self._case_input_hashes()
        hashes["physical,PX-R198"] = {"R1": "e" * 64, "R2": "f" * 64,
                                      "seeds": "0" * 64}
        with self.assertRaisesRegex(migration.MigrationError, "exactly R1 and R2"):
            migration.InjectedCaseSource(hashes)
        self.plan["case_input_hashes"] = hashes
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "case hashes must be exactly R1 and R2"):
            self._apply()

    def test_conflicting_duplicate_receipt_case_hash_is_rejected(self):
        arm = self._arm("idba-ud", "physical", "PX-R001")
        arm["input_sha256"] = {"R1": "0" * 64, "R2": "0" * 64}
        output = self.root / "conseq.csv"
        sched.record_outcome(self.root, arm, output, "success", seconds=1)
        with self.assertRaisesRegex(migration.MigrationError,
                                    "conflicting receipt case hashes"):
            self._apply()

    def test_image_pinned_only_target_is_not_admitted(self):
        staged = copy.deepcopy(self.staged_data)
        next(x for x in staged["candidates"] if x["id"] == TARGET)[
            "status"] = "image-pinned"
        write_json(self.staged, staged)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["new_plan_sha256"] = self._expected_digest()
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "staged tool is not eligible"):
            self._apply()

    def test_image_pinned_tool_gets_no_cohort_arms(self):
        staged = copy.deepcopy(self.staged_data)
        penguin = next(x for x in staged["candidates"] if x["id"] == "penguin")
        penguin["status"] = "image-pinned"
        penguin["image_sha256"] = "b" * 64
        penguin["image_evidence"] = self._evidence(
            staged, "penguin", "image", "b" * 64, suffix="-penguin")
        write_json(self.staged, staged)
        data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        self.assertNotIn("penguin", migration.eligible_tools(data))
        plan = sched.build_plan(
            self.staged, self._source(), self.root,
            provenance_root=self.root / "receipts")
        self.assertNotIn("penguin", plan["tools"])
        self.assertFalse(any(item["tool_id"] == "penguin"
                             for item in plan["arm_identities"]))

    def test_admitted_tool_cannot_be_downgraded_or_changed(self):
        staged = copy.deepcopy(self.staged_data)
        skesa = next(x for x in staged["candidates"] if x["id"] == "skesa")
        skesa["status"] = "image-pinned"
        write_json(self.staged, staged)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "previously admitted arm downgraded"):
            self._apply()

        staged = copy.deepcopy(self.staged_data)
        next(x for x in staged["candidates"] if x["id"] == "skesa")[
            "source_license"] = "MIT"
        write_json(self.staged, staged)
        self.plan["staged_registry_sha256"] = sha(self.staged)
        self.plan["new_plan_sha256"] = "0" * 64
        self._refresh_plan()
        with self.assertRaisesRegex(migration.MigrationError,
                                    "previously admitted identity changed"):
            self._apply()

    def test_image_replacement_needs_a_genuine_failed_pilot(self):
        active = self.promoted(json.loads(TEMPLATE.read_text()),
                               OLD_TOOLS + (TARGET,))
        staged = copy.deepcopy(active)
        old = next(x for x in active["candidates"] if x["id"] == "unicycler")
        old["status"] = "image-pinned"
        old["image_sha256"] = "b" * 64
        old["image_evidence"] = self._evidence(
            active, "unicycler", "image", "b" * 64, suffix="-unc")
        old["pilot_evidence"] = self._evidence(
            active, "unicycler", "pilot", "b" * 64, status="failure",
            suffix="-unc-failed")
        new = next(x for x in staged["candidates"] if x["id"] == "unicycler")
        new["status"] = "image-pinned"
        new["image_sha256"] = "c" * 64
        new["image_evidence"] = self._evidence(
            staged, "unicycler", "image", "c" * 64, suffix="-unc-replaced")
        new["pilot_evidence"] = copy.deepcopy(old["pilot_evidence"])
        write_json(self.active, active)
        write_json(self.staged, staged)
        staged_data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        # Ray remains the admitted target; replacing an unpiloted image after a
        # real failed pilot is the one allowed non-admitted identity change.
        migration.verify_additive(self.root, self.plan, self.staged, staged_data)

        good_pilot = self._evidence(
            active, "unicycler", "pilot", "b" * 64, suffix="-unc-success")
        old["pilot_evidence"] = good_pilot
        new["pilot_evidence"] = copy.deepcopy(good_pilot)
        write_json(self.active, active)
        write_json(self.staged, staged)
        with self.assertRaisesRegex(migration.MigrationError,
                                    "image replacement requires a failed pilot"):
            migration.verify_additive(self.root, self.plan, self.staged, staged_data)

    def test_other_nonadmitted_roster_changes_are_rejected(self):
        staged = copy.deepcopy(self.staged_data)
        next(x for x in staged["candidates"] if x["id"] == "unicycler")[
            "source_repo"] = "https://github.com/other/tool"
        write_json(self.staged, staged)
        staged_data = exploratory_policy.checked(
            self.staged, provenance_root=self.root / "receipts")
        with self.assertRaisesRegex(migration.MigrationError,
                                    "unvalidated roster change"):
            migration.verify_additive(self.root, self.plan, self.staged, staged_data)

    # --- recovery journal ---------------------------------------------------

    def test_journal_records_legacy_digest_before_swap(self):
        captured = []
        real_clear = migration._clear_journal

        def capture(path):
            captured.append(json.loads(Path(path).read_text()))
            real_clear(path)

        with mock.patch.object(migration, "_clear_journal", side_effect=capture):
            result = self._apply()
        self.assertEqual(result["status"], "applied")
        journal = captured[-1]
        self.assertEqual(journal["previous_checkpoint_plan_sha256"], "old-plan")
        self.assertEqual(journal["previous_checkpoint_completed"],
                         [self.receipt_ids[0]])
        self.assertEqual(journal["new_checkpoint_plan_sha256"],
                         self.plan["new_plan_sha256"])
        self.assertEqual(journal["before"]["active_registry_sha256"],
                         sha(self.root / "preserved" / WINDOW / "active.json"))
        self.assertFalse(migration._journal_path(self.root, self.plan).exists())

    def test_interrupted_checkpoint_swap_recovers_legacy_completion(self):
        self._interrupted_apply(self.checkpoint)
        result = self._apply()
        self.assertIn(result["status"], ("applied", "recovered"))
        after = json.loads(self.checkpoint.read_text())
        self.assertEqual(after["plan_sha256"], self.plan["new_plan_sha256"])
        self.assertEqual(after["completed"], sorted(self.receipt_ids))
        self.assertFalse(migration._journal_path(self.root, self.plan).exists())

    def test_identical_registry_legacy_digest_upgrade_without_journal(self):
        """Scheduler digest migration: identical registry, no new admission.

        active==staged, checkpoint has legacy plan digest, no receipt and no
        journal. This is a fresh legacy-only digest upgrade, not an interrupted
        swap (a swap would have written a journal before mutating state).
        """
        # Make active byte-identical to staged (tool already admitted, no new
        # admission). Checkpoint keeps a legacy digest that differs from the
        # scheduler-digest-migrated plan digest.
        self.active.write_bytes(self.staged.read_bytes())
        self.assertEqual(sha(self.active), sha(self.staged))
        self.assertNotEqual(
            json.loads(self.checkpoint.read_text())["plan_sha256"],
            self.plan["new_plan_sha256"])
        self.assertFalse(migration._journal_path(self.root, self.plan).exists())
        result = self._apply()
        self.assertIn(result["status"], ("applied", "recovered"))
        after = json.loads(self.checkpoint.read_text())
        self.assertEqual(after["plan_sha256"], self.plan["new_plan_sha256"])
        self.assertTrue(Path(result["receipt"]).is_file())
        self.assertFalse(migration._journal_path(self.root, self.plan).exists())

    def test_forged_journal_cannot_authorize_recovery(self):
        self._interrupted_apply(self.active)
        journal_path = migration._journal_path(self.root, self.plan)
        journal = json.loads(journal_path.read_text())
        journal["plan_sha256"] = "f" * 64
        write_json(journal_path, journal)
        with self.assertRaisesRegex(migration.MigrationError,
                                    "recovery journal does not match the plan"):
            self._apply()

    def test_receipt_alone_cannot_prove_applied_state(self):
        self._apply()
        write_json(self.active, self.active_data)
        with self.assertRaisesRegex(migration.MigrationError,
                                    "partial migration state has no recovery journal"):
            self._apply()

    def test_later_additive_advancement_supersedes_receipt(self):
        first = self._apply()
        later = json.loads(Path(first["receipt"]).read_text())
        later["plan_sha256"] = "a" * 64
        later["window_id"] = "20261125T000000Z"
        later["before"]["active_registry_sha256"] = self.plan[
            "staged_registry_sha256"]
        write_json(self.root / "receipts" / (
            "registry-migration-" + TARGET + "-20261125T000000Z.json"), later)
        write_json(self.active, self.active_data)
        result = self._apply()
        self.assertEqual(result["status"], "already-applied")

    def test_stale_journal_is_cleared_on_already_applied(self):
        self._apply()
        journal = migration._journal_path(self.root, self.plan)
        write_json(journal, {"schema": "stale-recovery-journal"})
        again = self._apply()
        self.assertEqual(again["status"], "already-applied")
        self.assertFalse(journal.exists())


if __name__ == "__main__":
    unittest.main()
