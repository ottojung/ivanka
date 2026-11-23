"""Adversarial proofs for canonical aliases and the resumable PX planner."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import exploratory_policy
from assembler_bench import px_cohort_scheduler as sched

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"
TOOLS = ("skesa", "minia")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    return path


def promotion_registry(root, promotions=None):
    data = json.loads(REGISTRY.read_text())
    for tool, changes in (promotions or {}).items():
        item = next(x for x in data["candidates"] if x["id"] == tool)
        item.update(changes)
    return write_json(root / "registry.json", data)


def make_receipt(root, data, tool, kind, extra, image_sha256=None):
    item = next(x for x in data["candidates"] if x["id"] == tool)
    receipt = {"schema": "ivanka.exploratory." + kind + ".receipt.v1",
               "tool_id": tool, "source_commit": item["source_commit"],
               "adapter_commit": data["adapter_branch_commits"][tool],
               "image_sha256": image_sha256 or item["image_sha256"],
               "qualifying": False}
    receipt.update(extra)
    path = write_json(root / "receipts" / (kind + "-" + tool + ".json"), receipt)
    return {"path": str(path), "sha256": sha(path)}


def cases_for(cohort, r1, r2, ids=None):
    """Build cases whose canonical alias comes from sorted source identity."""
    if ids is None:
        ids = [f"P{i:03d}" if cohort == "physical" else f"S{i:03d}"
               for i in range(1, sched.EXPECTED_COUNTS[cohort] + 1)]
    canonical = sched.canonical_aliases(ids, cohort)
    return [sched.CasePair(sid, canonical[sid], cohort, r1, r2) for sid in ids]


class CanonicalAliasTests(unittest.TestCase):
    def test_aliases_are_one_based_original_assembler_bench_aliases(self):
        self.assertEqual(sched._alias(1, "physical"), "PX-R001")
        self.assertEqual(sched._alias(198, "physical"), "PX-R198")
        self.assertEqual(sched._alias(1, "synthetic"), "PX-H001")
        self.assertEqual(sched._alias(464, "synthetic"), "PX-H464")
        for bad, cohort in ((0, "physical"), (199, "physical"),
                            (0, "synthetic"), (465, "synthetic")):
            with (self.subTest(position=bad, cohort=cohort),
                  self.assertRaisesRegex(ValueError, "out of cohort range")):
                sched._alias(bad, cohort)

    def test_alias_follows_sorted_source_identity_not_pilot_ordinal(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        r1, r2 = root / "R1.fastq.gz", root / "R2.fastq.gz"
        r1.write_bytes(b"r1")
        r2.write_bytes(b"r2")
        ids = [f"P{i:03d}" for i in range(1, 199)]
        shuffled = ids[::2] + ids[1::2]  # P053 is nowhere near list position 53
        cases = cases_for("physical", r1, r2, shuffled)
        source = sched.CohortSource(cases, cases_for("synthetic", r1, r2))
        self.assertEqual(source.case("physical", "PX-R053").source_id, "P053")
        self.assertEqual(source.case("physical", "PX-R001").source_id, "P001")
        # Assigning the pilot ordinal alias instead of the canonical one fails.
        target = cases[1]
        cases[1] = sched.CasePair(target.source_id, "PX-R001", "physical",
                                  r1, r2)
        with self.assertRaisesRegex(ValueError, "canonical original alias"):
            sched.CohortSource(cases, cases_for("synthetic", r1, r2))

    def test_literal_original_manifest_ordering_and_sha(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        r1, r2 = root / "R1.fastq.gz", root / "R2.fastq.gz"
        r1.write_bytes(b"r1")
        r2.write_bytes(b"r2")
        ids = [f"sample-{i:03d}" for i in range(1, 199)]
        shuffled = ids[::-1]
        manifest = root / "manifest.tsv"
        manifest.write_text("sample\tkive_run_id\n" + "".join(
            f"{sample}\trun-{sample}\n" for sample in shuffled))
        pinned = sha(manifest)
        cases = cases_for("physical", r1, r2, shuffled)
        with patch.object(sched, "PHYSICAL_MANIFEST_SHA256", pinned):
            source = sched.CohortSource(
                cases, cases_for("synthetic", r1, r2), physical_manifest=manifest)
        self.assertEqual(source.case("physical", "PX-R198").source_id,
                         "sample-198")
        self.assertEqual(source.case("physical", "PX-R053").source_id,
                         "sample-053")
        with (patch.object(sched, "PHYSICAL_MANIFEST_SHA256", "0" * 64),
              self.assertRaisesRegex(ValueError, "manifest SHA256 changed")):
            sched.CohortSource(cases, cases_for("synthetic", r1, r2),
                               physical_manifest=manifest)

    def test_literal_v6_cohort_ordering_sha_and_paired_input_sha(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cohort = json.loads(sched.SYNTHETIC_COHORT.read_bytes())
        records = cohort["cases"]
        ids = [item["id"] for item in records]
        ordered = sorted(ids)
        canonical = sched.canonical_aliases(ids, "synthetic")
        self.assertEqual(canonical[ordered[191]], "PX-H192")
        expected = {item["id"]: {
            "R1": item["sha256"]["reads/R1.fastq.gz"],
            "R2": item["sha256"]["reads/R2.fastq.gz"]} for item in records}
        paths = {}
        for item in records:
            r1 = root / (item["id"] + "-R1")
            r2 = root / (item["id"] + "-R2")
            r1.write_text(expected[item["id"]]["R1"])
            r2.write_text(expected[item["id"]]["R2"])
            paths[item["id"]] = (r1, r2)
        shuffled = [item["id"] for item in reversed(records)]
        cases = [sched.CasePair(sid, canonical[sid], "synthetic", *paths[sid])
                 for sid in shuffled]
        physical_r1, physical_r2 = root / "R1.fastq.gz", root / "R2.fastq.gz"
        physical_r1.write_bytes(b"r1")
        physical_r2.write_bytes(b"r2")
        physical = cases_for("physical", physical_r1, physical_r2)
        real_sha = sha(sched.SYNTHETIC_COHORT)

        def digest(path):
            target = Path(path)
            return real_sha if target == sched.SYNTHETIC_COHORT else target.read_text()

        with patch.object(sched, "sha256_file", side_effect=digest):
            source = sched.CohortSource(
                physical, cases, synthetic_cohort=sched.SYNTHETIC_COHORT)
        self.assertEqual(source.case("synthetic", "PX-H192").source_id,
                         ordered[191])
        # Swapping two cases' paired reads while keeping their canonical aliases
        # must be rejected instead of comparing mismatched aliased inputs.
        swapped = list(cases)
        a, b = swapped[0], swapped[1]
        swapped[0] = sched.CasePair(a.source_id, a.alias, a.cohort,
                                    b.r1, b.r2)
        with (patch.object(sched, "sha256_file", side_effect=digest),
              self.assertRaisesRegex(ValueError, "input SHA mismatch")):
            sched.CohortSource(physical, swapped,
                               synthetic_cohort=sched.SYNTHETIC_COHORT)

    def test_attested_paired_input_sha_blocks_mismatched_aliases(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        r1, r2 = root / "R1.fastq.gz", root / "R2.fastq.gz"
        r1.write_bytes(b"r1")
        r2.write_bytes(b"r2")
        cases = cases_for("physical", r1, r2)
        distinct = {}
        for index in (0, 1):
            first, second = root / f"case-{index}-R1.fastq.gz", root / f"case-{index}-R2.fastq.gz"
            first.write_bytes(f"r1-{index}".encode())
            second.write_bytes(f"r2-{index}".encode())
            distinct[cases[index].source_id] = (first, second)
            cases[index] = sched.CasePair(cases[index].source_id,
                                          cases[index].alias, "physical",
                                          first, second)
        expected = {case.source_id: case.input_hashes() for case in cases}
        synthetic = cases_for("synthetic", r1, r2)
        sched.CohortSource(cases, synthetic,
                           attested_inputs={"physical": expected})
        swapped = list(cases)
        a, b = swapped[0], swapped[1]
        swapped[0] = sched.CasePair(a.source_id, a.alias, "physical",
                                    b.r1, b.r2)
        swapped[1] = sched.CasePair(b.source_id, b.alias, "physical",
                                    a.r1, a.r2)
        with self.assertRaisesRegex(ValueError, "input SHA mismatch"):
            sched.CohortSource(swapped, synthetic,
                               attested_inputs={"physical": expected})


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.px = self.root / "px"
        self.px.mkdir()
        self.r1 = self.root / "private-R1.fastq.gz"
        self.r2 = self.root / "private-R2.fastq.gz"
        self.r1.write_bytes(b"@private\nACGT\n+\n!!!!\n")
        self.r2.write_bytes(b"@private\nTGCA\n+\n!!!!\n")
        self.policy = patch.object(exploratory_policy, "PROVENANCE_ROOT", self.root)
        self.policy.start()
        self.addCleanup(self.policy.stop)

    def source(self):
        return sched.CohortSource(cases_for("physical", self.r1, self.r2),
                                  cases_for("synthetic", self.r1, self.r2))

    def promoted_registry(self, tools=TOOLS, stage="pilot"):
        data = json.loads(REGISTRY.read_text())
        promotions = {}
        for tool in tools:
            changes = {"status": stage, "image_sha256": "b" * 64}
            changes["image_evidence"] = make_receipt(
                self.root, data, tool, "image",
                {"native_binary_sha256": "a" * 64}, "b" * 64)
            if stage == "pilot":
                changes["pilot_evidence"] = make_receipt(
                    self.root, data, tool, "pilot", {
                        "physical": {"source_input_sha256": "c" * 64,
                                     "status": "success"},
                        "synthetic": {"source_input_sha256": "d" * 64,
                                      "status": "success"}}, "b" * 64)
            promotions[tool] = changes
        return promotion_registry(self.root, promotions)

    def test_source_pinned_roster_has_no_eligible_arm(self):
        with self.assertRaisesRegex(ValueError, "no pilot/image-proof"):
            sched.build_plan(REGISTRY, self.source(), self.px)

    def test_image_proof_is_required_for_admission(self):
        data = json.loads(REGISTRY.read_text())
        item = next(x for x in data["candidates"] if x["id"] == "skesa")
        item.update(status="image-pinned", image_sha256="b" * 64)
        registry = write_json(self.root / "no-proof.json", data)
        with self.assertRaisesRegex(ValueError, "image proof|image receipt"):
            sched.build_plan(registry, self.source(), self.px)

    def test_pilot_proof_promotes_tools_in_registry_order(self):
        registry = self.promoted_registry()
        plan = sched.build_plan(registry, self.source(), self.px)
        self.assertEqual(plan["tools"], list(TOOLS))
        self.assertEqual(plan["total_arms"], 2 * 662)
        self.assertEqual(plan["pending_arms"], 2 * 662)
        self.assertEqual([a["alias"] for a in plan["pending"][:198]],
                         [sched._alias(i, "physical")
                          for i in range(1, 199)])
        self.assertEqual(plan["pending"][198]["tool_id"], "minia")
        self.assertEqual(plan["pending"][198]["alias"], "PX-R001")
        self.assertEqual(plan["pending"][396]["alias"], "PX-H001")
        self.assertEqual(plan["pending"][396]["tool_id"], "skesa")
        self.assertEqual(plan["pending"][860]["alias"], "PX-H001")
        self.assertEqual(plan["pending"][860]["tool_id"], "minia")
        self.assertTrue(all(a["cohort"] == "physical"
                            for a in plan["pending"][:396]))
        self.assertTrue(all(a["cohort"] == "synthetic"
                            for a in plan["pending"][396:]))
        self.assertFalse(plan["qualifying"])

    def test_cohort_size_and_alias_validation(self):
        cases = cases_for("physical", self.r1, self.r2)[:197]
        with self.assertRaisesRegex(ValueError, "cohort size"):
            sched.CohortSource(cases, [])
        cases = cases_for("physical", self.r1, self.r2)
        cases[0] = sched.CasePair(cases[0].source_id, "PX-H001", "physical",
                                  self.r1, self.r2)
        with self.assertRaisesRegex(ValueError, "canonical original alias"):
            sched.CohortSource(cases, cases_for("synthetic", self.r1, self.r2))

    def test_read_derived_seed_provenance_is_enforced(self):
        cases = cases_for("physical", self.r1, self.r2)
        first = cases[0]
        cases[0] = sched.CasePair(first.source_id, first.alias, first.cohort,
                                  self.r1, self.r2, seeds=self.r1,
                                  seeds_provenance={"kind": "reference-derived"})
        with self.assertRaisesRegex(ValueError, "read-derived"):
            sched.CohortSource(cases, cases_for("synthetic", self.r1, self.r2))

    def test_success_and_failure_receipts_are_terminal_and_resumable(self):
        registry = self.promoted_registry()
        plan = sched.build_plan(registry, self.source(), self.px)
        output = self.root / "conseq.csv"
        output.write_bytes(b"consensus\n")
        first, second = plan["pending"][0], plan["pending"][1]
        good = sched.record_outcome(self.px, first, output, "success",
                                    seconds=12.5, peak_rss=3_000_000_000)
        self.assertEqual(good["output_sha256"], sha(output))
        sched.record_outcome(self.px, second, None, "failure",
                             failure_reason="timeout")
        self.assertEqual(sched.verify_receipt(self.px, first), good)
        resumed = sched.build_plan(registry, self.source(), self.px)
        self.assertEqual(resumed["accepted_arms"], 2)
        self.assertEqual(resumed["pending_arms"], 2 * 662 - 2)
        remaining = {sched.receipt_id(a) for a in resumed["pending"]}
        self.assertNotIn(sched.receipt_id(first), remaining)
        self.assertNotIn(sched.receipt_id(second), remaining)

    def test_outcomes_fail_closed(self):
        registry = self.promoted_registry()
        arm = sched.build_plan(registry, self.source(), self.px)["pending"][0]
        output = self.root / "conseq.csv"
        output.write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "terminal"):
            sched.record_outcome(self.px, arm, output, "running")
        with self.assertRaisesRegex(ValueError, "positive runtime"):
            sched.record_outcome(self.px, arm, output, "success", seconds=0)
        with self.assertRaisesRegex(ValueError, "final MAX"):
            sched.record_outcome(self.px, arm, output.with_name("contigs.fa"),
                                 "success", seconds=1)
        with self.assertRaisesRegex(ValueError, "unclassified failure"):
            sched.record_outcome(self.px, arm, None, "failure", failure_reason="oops")
        sched.record_outcome(self.px, arm, output, "success", seconds=1)
        with self.assertRaisesRegex(ValueError, "not be recomputed"):
            sched.record_outcome(self.px, arm, output, "success", seconds=2)

    def test_tampered_receipt_or_index_stops_resume(self):
        registry = self.promoted_registry()
        arm = sched.build_plan(registry, self.source(), self.px)["pending"][0]
        output = self.root / "conseq.csv"
        output.write_bytes(b"x")
        sched.record_outcome(self.px, arm, output, "success", seconds=1)
        path = sched.receipt_path(self.px, arm)
        raw = json.loads(path.read_text())
        raw["output_sha256"] = "0" * 64
        path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, "unindexed or changed"):
            sched.verify_receipt(self.px, arm)
        with self.assertRaisesRegex(ValueError, "unindexed or changed"):
            sched.build_plan(registry, self.source(), self.px)

    def test_private_paths_never_reach_public_structures(self):
        with self.assertRaisesRegex(ValueError, "private identifier"):
            sched._assert_public({"path": "/workspace/secret-R1.fastq.gz"})
        view = self.source().public_view()
        self.assertNotIn(".fastq", json.dumps(view))
        self.assertNotIn("/workspace", json.dumps(view))
        registry = self.promoted_registry()
        plan = sched.build_plan(registry, self.source(), self.px)
        self.assertNotIn(".fastq", json.dumps(plan))

    def test_posthoc_scorer_is_source_frozen_and_bound_to_hashed_output(self):
        class FrozenScorer:
            source_sha256 = "e" * 64

            def score(self, alias, cohort, output_sha256):
                return {"alias": alias, "outcome": "success",
                        "score": 101.5, "seconds": 3.25,
                        "output_sha256": output_sha256}

        registry = self.promoted_registry()
        arm = sched.build_plan(registry, self.source(), self.px)["pending"][0]
        with self.assertRaisesRegex(ValueError, "terminal successful"):
            sched.posthoc_score(self.px, arm, FrozenScorer(), "e" * 64)
        output = self.root / "conseq.csv"
        output.write_bytes(b"x")
        sched.record_outcome(self.px, arm, output, "success", seconds=1)
        result = sched.posthoc_score(self.px, arm, FrozenScorer(), "e" * 64)
        self.assertEqual(result["schema"], sched.RESULT_SCHEMA)
        self.assertEqual(result["expected_sample_count"], 198)
        path, digest = sched.write_results(self.px, arm, result)
        self.assertEqual(digest, sha(path))
        with self.assertRaisesRegex(ValueError, "scorer identity changed"):
            sched.posthoc_score(self.px, arm, FrozenScorer(), "f" * 64)

    def test_checkpoint_is_atomic_verified_and_never_authoritative(self):
        registry = self.promoted_registry()
        plan = sched.build_plan(registry, self.source(), self.px)
        with (patch.object(sched.os, "replace", side_effect=OSError("crash")),
              self.assertRaises(OSError)):
            sched.write_checkpoint(self.px, plan, [])
        self.assertFalse(sched.checkpoint_path(self.px).exists())
        self.assertEqual(sched.resume(plan, self.px), plan["pending"])
        arm = plan["pending"][0]
        sched.write_checkpoint(self.px, plan, [sched.receipt_id(arm)])
        self.assertEqual(sched.resume(plan, self.px), plan["pending"][1:])
        raw = json.loads(sched.checkpoint_path(self.px).read_text())
        raw["completed"].append("not-an-arm")
        sched.checkpoint_path(self.px).write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, "unknown arm"):
            sched.resume(plan, self.px)

    def test_admission_reuses_capped_guard_and_stops_on_disk_pressure(self):
        registry = self.promoted_registry()
        root = self.px
        store = self.root / "store"
        store.mkdir(exist_ok=True)
        baseline = {"schema": "ivanka.exploratory.storage-baseline.v1",
                    "root": str(root), "image_store": str(store),
                    "workspace": str(self.root), "base_store_bytes": 0,
                    "frozen_manifest_sha256":
                        "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
                    "active_job": None}
        scoped = json.loads(REGISTRY.read_text())["policy"]
        scoped["dedicated_image_store_root"] = str(store)
        scoped["dedicated_podman_storage_conf"] = str(self.root / "storage.conf")
        patched = patch.object(sched.exploratory_policy, "checked",
                               return_value={"policy": scoped})
        patched.start()
        self.addCleanup(patched.stop)
        with patch("assembler_bench.exploratory_space.available",
                   return_value=100 * 1024**3):
            decision = sched.admit_arm(registry, baseline, root, 1024**3)
        self.assertEqual(decision["admitted_reservation_bytes"], 1024**3)
        with (patch("assembler_bench.exploratory_space.available",
                    return_value=0),
              self.assertRaisesRegex(ValueError, "disk budget|workspace reserve")):
            sched.admit_arm(registry, baseline, root, 1024**3)
        with self.assertRaisesRegex(ValueError, "reservation"):
            sched.admit_arm(registry, baseline, root, 8 * 1024**3)


if __name__ == "__main__":
    unittest.main()
