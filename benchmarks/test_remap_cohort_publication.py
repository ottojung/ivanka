import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from assembler_bench import px_ram_semantics as ram
from assembler_bench import remap_cohort_publication as pub
from assembler_bench import remap_diagnostic as display
from assembler_bench import remap_runner as runner

STAMP = "20261127T120000000000Z"
TOKEN = "deadbeef"


def make_cases(root, cohort, aliases):
    cases = []
    for alias in aliases:
        reads = root / "reads" / alias
        reads.mkdir(parents=True)
        names = (f"{alias}_L001_R1_001.fastq.gz",
                 f"{alias}_L001_R2_001.fastq.gz")
        digests = []
        for name in names:
            payload = f"@{name}\nACGT\n+\nIIII\n".encode()
            (reads / name).write_bytes(payload)
            digests.append(hashlib.sha256(payload).hexdigest())
        attempt = root / "attempt" / alias
        attempt.mkdir(parents=True)
        timer = root / "timer.py"
        timer.write_text("# timer\n")
        cases.append(runner.Case(
            alias=alias, cohort=cohort,
            r1_sha256=digests[0], r2_sha256=digests[1],
            reads_dir=str(reads), attempt_dir=str(attempt),
            timer=str(timer), cidfile=str(attempt / "cid"),
            storage_root=str(root / "store"), runroot=str(root / "runroot"),
            name=f"podman-name-remap-{alias}-test",
            r1_name=names[0], r2_name=names[1]))
    return cases


def measured_receipt(plan):
    resource = {
        ram.METHOD_KEY: ram.COMPARABLE_METHOD,
        ram.VERSION_KEY: ram.COMPARABLE_METHOD_VERSION,
        ram.SCOPE_KEY: ram.COMPARABLE_SCOPE,
        "samples": 3,
        "observation_ended": True,
        "peak_rss_bytes": 3_000_000_000,
        "bound_cid": "a" * 64,
        "guard_receipt": {
            "bound_cid": "a" * 64,
            "rss_limit_bytes": 4_000_000_000,
            "wall_seconds": 2400,
            "cpu_allocation": 2,
            "kernel_enforcement": False,
        },
    }
    return runner.build_receipt(
        plan, status="measured", score=12.5, seconds=120.0,
        outputs={"conseq_csv_sha256": "b" * 64}, resource=resource)


def make_delivery(root, cohort, aliases, statuses):
    cases = make_cases(root, cohort, aliases)
    manifest = runner.input_manifest(cases)
    plans = [runner.plan_case(case, manifest, stamp=STAMP, token=TOKEN)
             for case in cases]
    receipts = []
    for plan, status in zip(plans, statuses):
        if status == "measured":
            receipts.append(measured_receipt(plan))
        else:
            receipts.append(runner.build_receipt(
                plan, status=status, failure_reason=f"typed-{status}"))
    return {"run_id": plans[0]["run_id"], "receipts": receipts,
            "plans": plans}, cases


def make_report(deliveries):
    samples = {}
    for delivery in deliveries.values():
        for plan in delivery["plans"]:
            samples[plan["alias"]] = {
                "alias": plan["alias"], "score": {}, "seconds": {},
                "diagnostics": {}, "failures": [], "outcome": "success"}
    runs = []
    for cohort in ("real", "synthetic"):
        aliases = sorted(alias for alias in samples
                         if alias.startswith("R" if cohort == "real" else "H"))
        runs.append({
            "id": f"fixture-{cohort}", "cohort": cohort,
            "tools": ["iva", "ivanka"], "roster": [],
            "tool_labels": {"iva": "IVA", "ivanka": "Ivanka"},
            "expected_sample_count": len(aliases),
            "sample_count": len(aliases),
            "samples": [samples[alias] for alias in aliases],
            "dominance_matrix": {},
        })
    return {
        "schema": "ivanka.assembler-bench.public.v1",
        "title": "fixture",
        "psi": {"alignment": [{"r": 0.0, "value": 1.0}]},
        "runs": runs,
    }


def make_registry(deliveries):
    return {
        "schema": display.REGISTRY_SCHEMA, "tool_id": display.TOOL_ID,
        "label": display.LABEL, "method_kind": display.METHOD_KIND,
        "de_novo": False,
        "invocation": "micall analyze sample --all_projects --keep_scratch",
        "image": {"sha256": runner.IMAGE_ID, "reuse": "frozen-clinical-base"},
        "source_commit": runner.SOURCE_COMMIT,
        "frozen_master_commit": runner.SOURCE_COMMIT,
        "reference_panel_sha256": runner.PANEL_SHA256,
        "inputs": {
            cohort: delivery["plans"][0]["inputs"]["canonical_manifest_sha256"]
            for cohort, delivery in deliveries.items()},
        "guard": {
            "max_wall_seconds": 2400, "max_rss_bytes": 4_000_000_000,
            "cpu_allocation": 2, "exclusive_execution_slot": True,
            "kernel_enforcement": False,
            "minimum_free_bytes": 32 * 1024**3},
        "acceptance_effect": "none", "enabled": True,
    }


class CohortPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.deliveries = {}
        self.deliveries["real"], _ = make_delivery(
            self.root / "real", "real", ["R001", "R002"],
            ["measured", "failed"])
        self.deliveries["synthetic"], _ = make_delivery(
            self.root / "synthetic", "synthetic", ["H001", "H002"],
            ["measured", "unavailable"])

    def test_both_cohorts_fold_additively_with_invariance_proof(self):
        report = make_report(self.deliveries)
        artifact = pub.build_cohort_publication(
            report=report, registry=make_registry(self.deliveries),
            deliveries=self.deliveries)
        self.assertEqual(artifact["schema"], pub.COHORT_SCHEMA)
        self.assertEqual(artifact["qualification_claim"], "NONE")
        self.assertFalse(artifact["executed_here"])
        self.assertFalse(artifact["published_here"])
        self.assertFalse(artifact["de_novo"])
        self.assertTrue(artifact["psi_unchanged"])
        self.assertTrue(artifact["invariance_proven"])
        self.assertEqual(artifact["case_count"], 4)
        self.assertEqual([entry["cohort"] for entry in artifact["cohorts"]],
                         ["real", "synthetic"])
        self.assertEqual(
            [entry["status_counts"] for entry in artifact["cohorts"]],
            [{"failed": 1, "measured": 1},
             {"measured": 1, "unavailable": 1}])
        merged = artifact["report"]
        self.assertEqual(merged["psi"], report["psi"])
        for run in merged["runs"]:
            self.assertIn(display.TOOL_ID, run["tools"])
            for sample in run["samples"]:
                arm = sample["diagnostics"][display.TOOL_ID]
                for key in runner.NA_METRICS:
                    self.assertIsNone(arm[key])
        self.assertEqual(display.validate_display_contract(merged), 2)

    def test_qualification_view_is_identical_with_and_without_remap(self):
        report = make_report(self.deliveries)
        before = pub._digest(pub._decision_view(report))
        artifact = pub.build_cohort_publication(
            report=report, registry=make_registry(self.deliveries),
            deliveries=self.deliveries)
        self.assertEqual(
            pub._digest(pub._decision_view(artifact["report"])), before)
        self.assertEqual(artifact["qualification_view_digest"], before)

    def test_pilot_subset_needs_only_one_cohort(self):
        report = make_report(self.deliveries)
        only = {"real": self.deliveries["real"]}
        artifact = pub.build_cohort_publication(
            report=report, registry=make_registry(only), deliveries=only)
        self.assertEqual(artifact["case_count"], 2)
        self.assertEqual([entry["cohort"] for entry in artifact["cohorts"]],
                         ["real"])

    def test_redelivery_is_idempotent(self):
        report = make_report(self.deliveries)
        registry = make_registry(self.deliveries)
        first = pub.build_cohort_publication(
            report=report, registry=registry, deliveries=self.deliveries)
        second = pub.build_cohort_publication(
            report=first["report"], registry=registry,
            deliveries=self.deliveries)
        self.assertEqual(second["case_count"], 4)
        for entry in second["cohorts"]:
            self.assertEqual(entry["joined_samples"], 0)
        self.assertEqual(second["report"], first["report"])

    def test_rejects_rows_derived_attestation(self):
        report = make_report(self.deliveries)
        with self.assertRaises(ValueError):
            pub.build_cohort_publication(
                report=report, registry=make_registry(self.deliveries),
                deliveries={"real": {
                    "run_id": self.deliveries["real"]["run_id"],
                    "receipts": self.deliveries["real"]["receipts"],
                    "plans": runner.build_rows(
                        self.deliveries["real"]["receipts"],
                        run_id=self.deliveries["real"]["run_id"],
                        cohort="real")["cases"]}})

    def test_rejects_tampered_receipt_and_wrong_cohort(self):
        report = make_report(self.deliveries)
        registry = make_registry(self.deliveries)
        tampered = copy.deepcopy(self.deliveries)
        tampered["real"]["receipts"][0]["score"] = 99.0
        with self.assertRaises(ValueError):
            pub.build_cohort_publication(
                report=report, registry=registry, deliveries=tampered)
        swapped = copy.deepcopy(self.deliveries)
        swapped["real"]["receipts"][0]["cohort"] = "synthetic"
        with self.assertRaises(ValueError):
            pub.build_cohort_publication(
                report=report, registry=registry, deliveries=swapped)

    def test_rejects_unknown_cohort_and_empty_deliveries(self):
        report = make_report(self.deliveries)
        registry = make_registry(self.deliveries)
        with self.assertRaises(ValueError):
            pub.build_cohort_publication(
                report=report, registry=registry,
                deliveries={"truth": self.deliveries["real"]})
        with self.assertRaises(ValueError):
            pub.build_cohort_publication(
                report=report, registry=registry, deliveries={})


if __name__ == "__main__":
    unittest.main()
