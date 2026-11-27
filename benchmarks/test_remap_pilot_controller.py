import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from assembler_bench import guarded_canary_launcher as launcher
from assembler_bench import remap_pilot_controller as ctl
from assembler_bench import remap_runner as runner
from assembler_bench import remap_diagnostic as display

STAMP = "20261127T120000000000Z"
TOKEN = "deadbeef"
R1 = "R001_L001_R1_001.fastq.gz"
R2 = "R001_L001_R2_001.fastq.gz"


def make_case(root: Path, alias="R001", cohort="real"):
    reads = root / "reads" / alias
    reads.mkdir(parents=True)
    for name in (R1, R2):
        (reads / name).write_bytes(f"@{name}\nACGT\n+\nIIII\n".encode())
    attempt = root / "attempt" / alias
    attempt.mkdir(parents=True)
    timer = root / "timer.py"
    timer.write_text("# timer\n")
    return runner.Case(
        alias=alias, cohort=cohort,
        r1_sha256=launcher.sha256_file(reads / R1),
        r2_sha256=launcher.sha256_file(reads / R2),
        reads_dir=str(reads), attempt_dir=str(attempt),
        timer=str(timer), cidfile=str(attempt / "cid"),
        storage_root=str(root / "store"), runroot=str(root / "runroot"),
        name=f"podman-name-remap-{alias}-test",
        r1_name=R1, r2_name=R2,
    )


def make_plan(root: Path, alias="R001", cohort="real"):
    case = make_case(root, alias=alias, cohort=cohort)
    manifest = runner.input_manifest([case])
    plan = runner.plan_case(case, manifest, stamp=STAMP, token=TOKEN)
    return case, plan


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case, self.plan = make_plan(self.root)

    def ok(self, **kw):
        args = dict(plan=self.plan, free_bytes=40 * 1024**3,
                    exclusive_slot=True, image_present=True, image_rebuilt=False)
        args.update(kw)
        return ctl.preflight(**args)

    def test_admitted_when_all_guards_hold(self):
        p = self.ok()
        self.assertTrue(p["admitted"])
        self.assertEqual(p["reasons"], [])
        self.assertTrue(p["no_truth_mounted"])
        self.assertTrue(p["capacity"]["capacity_admitted"])

    def test_rejects_low_reserve(self):
        p = self.ok(free_bytes=32 * 1024**3 - 1)
        self.assertFalse(p["admitted"])
        self.assertIn("reserve", p["reasons"])

    def test_rejects_missing_exclusive_slot(self):
        p = self.ok(exclusive_slot=False)
        self.assertFalse(p["admitted"])
        self.assertIn("exclusive_slot", p["reasons"])

    def test_rejects_truth_mounted(self):
        bad = dict(self.plan)
        bad["reference"] = dict(self.plan["reference"], truth_mounted=True)
        p = self.ok(plan=bad)
        self.assertFalse(p["admitted"])
        self.assertIn("reference_truth_mounted", p["reasons"])

    def test_rejects_truth_path_in_argv(self):
        bad = dict(self.plan)
        bad["argv"] = list(self.plan["argv"]) + ["-v", "/tmp/hidden-truth:/truth:ro"]
        p = self.ok(plan=bad)
        self.assertFalse(p["admitted"])
        self.assertIn("truth_mounted", p["reasons"])

    def test_rejects_image_rebuilt_or_missing(self):
        self.assertIn("image_rebuilt", self.ok(image_rebuilt=True)["reasons"])
        self.assertIn("image_missing", self.ok(image_present=False)["reasons"])

    def test_rejects_guard_drift(self):
        bad = dict(self.plan)
        bad["guard"] = dict(self.plan["guard"], wall_seconds=3600)
        p = self.ok(plan=bad)
        self.assertFalse(p["admitted"])
        self.assertIn("guard_bounds", p["reasons"])

    def test_rejects_read_hash_drift(self):
        bad = dict(self.plan)
        bad["inputs"] = dict(self.plan["inputs"])
        bad["inputs"]["read_sha256"] = {"R1": "0" * 64, "R2": "1" * 64}
        bad["inputs"]["paired_input_sha256"] = "bad"
        p = self.ok(plan=bad)
        self.assertFalse(p["admitted"])
        self.assertIn("attested_reads", p["reasons"])


class ExecuteCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case, self.plan = make_plan(self.root)
        self.pilot_case = ctl.PilotCase(case=self.case)
        self.preflight = ctl.preflight(
            self.plan, free_bytes=40 * 1024**3, exclusive_slot=True)

    def fake_runner(self, *, returncode=0, peak_rss=3_000_000_000,
                    wall_seconds=12.5, timed_out=False, write_final_max=True):
        def run(plan, output_dir, attempt_dir):
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            log = Path(attempt_dir) / "logs" / "container.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("ok\n")
            if write_final_max:
                (output_dir / "conseq.csv").write_text("name,consensus\nA,ACGT\n")
            return {
                "returncode": returncode,
                "peak_rss_bytes": peak_rss,
                "samples": 5,
                "observation_ended": True,
                "wall_seconds": wall_seconds,
                "timed_out": timed_out,
                "bound_cid": "a" * 64,
                "guard_receipt": {
                    "bound_cid": "a" * 64,
                    "rss_limit_bytes": 4_000_000_000,
                    "wall_seconds": 2400,
                    "cpu_allocation": 2,
                    "kernel_enforcement": False,
                },
                "log_paths": {"container.log": str(log)},
            }
        return run

    def test_measured_case_emits_distinct_receipt_and_retains_logs(self):
        scorer = lambda p, c, o: {
            "schema": ctl.SCORING_SCHEMA, "method": ctl.PHYSICAL_SCORING_METHOD,
            "cohort": "real", "score": 321.0,
            "reference_panel_sha256": "f" * 64, "best_reference": "HXB2",
            "multitruth": None,
        }
        receipt = ctl.execute_case(
            self.pilot_case, plan=self.plan, preflight_result=self.preflight,
            runner=self.fake_runner(), output_dir=self.root / "out",
            attempt_dir=self.root / "att", scorer=scorer)
        self.assertEqual(receipt["status"], "measured")
        self.assertEqual(receipt["score"], 321.0)
        self.assertEqual(receipt["qualification_claim"], "NONE")
        self.assertTrue(receipt["receipt_sha256"])
        self.assertTrue((self.root / "att" / "receipt.json").is_file())
        self.assertTrue((self.root / "att" / "retention.json").is_file())
        self.assertTrue((self.root / "att" / "logs" / "container.log").is_file())
        for k in runner.NA_METRICS:
            self.assertIsNone(receipt["diagnostics"][k])
            self.assertIn(k, receipt["unavailable"])

    def test_distinct_receipts_for_distinct_runs(self):
        r1 = ctl.execute_case(
            self.pilot_case, plan=self.plan, preflight_result=self.preflight,
            runner=self.fake_runner(), output_dir=self.root / "o1",
            attempt_dir=self.root / "a1",
            scorer=lambda p, c, o: {"schema": ctl.SCORING_SCHEMA, "method": "m",
                                    "cohort": "real", "score": 1.0,
                                    "reference_panel_sha256": "f" * 64,
                                    "best_reference": "x", "multitruth": None})
        case2 = make_case(self.root / "second", alias="R002")
        manifest2 = runner.input_manifest([case2])
        plan2 = runner.plan_case(case2, manifest2, stamp=STAMP, token="other01")
        p2 = ctl.preflight(plan2, free_bytes=40 * 1024**3, exclusive_slot=True)
        r2 = ctl.execute_case(
            ctl.PilotCase(case=case2), plan=plan2, preflight_result=p2,
            runner=self.fake_runner(), output_dir=self.root / "o2",
            attempt_dir=self.root / "a2",
            scorer=lambda p, c, o: {"schema": ctl.SCORING_SCHEMA, "method": "m",
                                    "cohort": "real", "score": 2.0,
                                    "reference_panel_sha256": "f" * 64,
                                    "best_reference": "x", "multitruth": None})
        self.assertNotEqual(r1["receipt_sha256"], r2["receipt_sha256"])
        self.assertNotEqual(r1["run_id"], r2["run_id"])

    def test_preflight_failure_yields_failed_receipt_no_execution(self):
        called = {"n": 0}
        def run(*a, **k):
            called["n"] += 1
            return {}
        bad = ctl.preflight(self.plan, free_bytes=0, exclusive_slot=False)
        receipt = ctl.execute_case(
            self.pilot_case, plan=self.plan, preflight_result=bad,
            runner=run, output_dir=self.root / "o", attempt_dir=self.root / "a")
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("preflight:", receipt["failure_reason"])
        self.assertEqual(called["n"], 0)

    def test_missing_final_max_is_failure(self):
        receipt = ctl.execute_case(
            self.pilot_case, plan=self.plan, preflight_result=self.preflight,
            runner=self.fake_runner(write_final_max=False),
            output_dir=self.root / "o", attempt_dir=self.root / "a",
            scorer=lambda *a: (_ for _ in ()).throw(AssertionError("no score")))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_reason"], "no_final_max")
        self.assertIsNone(receipt["score"])

    def test_synthetic_multitruth_diagnostic_is_posthoc_only(self):
        case, plan = make_plan(self.root / "syn", alias="H001", cohort="synthetic")
        p = ctl.preflight(plan, free_bytes=40 * 1024**3, exclusive_slot=True)
        scorer = lambda p, c, o: {
            "schema": ctl.SCORING_SCHEMA, "method": ctl.SYNTHETIC_SCORING_METHOD,
            "cohort": "synthetic", "score": 900.0, "truth_sha256": "e" * 64,
            "reference_count": 2,
            "multitruth": {"diagnostic_only": True, "truth_count": 2,
                           "all_abundant_truths_scored": True,
                           "per_truth": {"t1": {"score": 0.9}, "t2": {"score": 0.8}}},
        }
        receipt = ctl.execute_case(
            ctl.PilotCase(case=case), plan=plan, preflight_result=p,
            runner=self.fake_runner(), output_dir=self.root / "os",
            attempt_dir=self.root / "as", scorer=scorer)
        self.assertEqual(receipt["status"], "measured")
        mt = receipt["diagnostics"]["multitruth_diagnostic"]
        self.assertTrue(mt["diagnostic_only"])
        self.assertEqual(mt["truth_count"], 2)
        ref = receipt["reference"]
        self.assertFalse(ref["truth_mounted"])
        self.assertFalse(ref["synthetic_truth_mounted"])
        self.assertFalse(ref["scoring_panel_mounted"])


class HardenedContractTests(unittest.TestCase):
    """Integration with PR548 hardened receipt and PR549 attested inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def base(self, cohort="real", alias="R001"):
        case, plan = make_plan(self.root / cohort, alias=alias, cohort=cohort)
        pre = ctl.preflight(plan, free_bytes=40 * 1024**3, exclusive_slot=True)
        return case, plan, pre

    def scorer(self, score):
        return lambda p, c, o: {
            "schema": ctl.SCORING_SCHEMA, "method": "posthoc",
            "cohort": p["cohort"], "score": score,
            "reference_panel_sha256": "f" * 64,
            "best_reference": "x", "multitruth": None,
        }

    def test_measured_receipt_carries_attested_ram_and_guard_binding(self):
        case, plan, pre = self.base()
        receipt = ctl.execute_case(
            ctl.PilotCase(case=case), plan=plan, preflight_result=pre,
            runner=ExecuteCaseTests.fake_runner(self), output_dir=self.root / "o",
            attempt_dir=self.root / "a", scorer=self.scorer(123.5))
        self.assertEqual(receipt["status"], "measured")
        self.assertEqual(receipt["resource"]["bound_cid"], "a" * 64)
        self.assertEqual(receipt["diagnostics"]["peak_ram_observed_mib"],
                         round(3_000_000_000 / 1048576, 6))
        self.assertNotIn("peak_ram_unavailable_reason", receipt["diagnostics"])

    def test_missing_guard_receipt_fails_closed(self):
        case, plan, pre = self.base()
        def bad_runner(*args, **kwargs):
            result = ExecuteCaseTests.fake_runner(self)(*args, **kwargs)
            result.pop("guard_receipt")
            return result
        receipt = ctl.execute_case(
            ctl.PilotCase(case=case), plan=plan, preflight_result=pre,
            runner=bad_runner, output_dir=self.root / "o",
            attempt_dir=self.root / "a", scorer=self.scorer(1.0))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_reason"],
                         "posthoc_scoring_error:ValueError")
        self.assertIsNone(receipt["score"])

    def test_nonfinite_score_is_rejected(self):
        case, plan, pre = self.base()
        receipt = ctl.execute_case(
            ctl.PilotCase(case=case), plan=plan, preflight_result=pre,
            runner=ExecuteCaseTests.fake_runner(self), output_dir=self.root / "o",
            attempt_dir=self.root / "a", scorer=self.scorer(math.nan))
        self.assertEqual(receipt["status"], "failed")
        self.assertIsNone(receipt["score"])

    def test_attested_mapping_is_not_rows_derived_and_joins_display(self):
        case, plan, pre = self.base()
        receipt = ctl.execute_case(
            ctl.PilotCase(case=case), plan=plan, preflight_result=pre,
            runner=ExecuteCaseTests.fake_runner(self), output_dir=self.root / "o",
            attempt_dir=self.root / "a", scorer=self.scorer(77.0))
        rows = runner.build_rows([receipt], run_id=plan["run_id"], cohort="real")
        mapping = ctl.attested_input_mapping([plan])
        ctl.require_independent_attested_mapping(mapping, rows)
        # A rows object used as attested_inputs is self-attestation and must
        # be refused by the controller boundary.
        with self.assertRaises(ValueError):
            ctl.require_independent_attested_mapping(rows, rows)
        registry = {
            "schema": display.REGISTRY_SCHEMA, "tool_id": display.TOOL_ID,
            "label": display.LABEL, "method_kind": display.METHOD_KIND,
            "de_novo": False,
            "invocation": "micall analyze sample --all_projects --keep_scratch",
            "image": {"sha256": runner.IMAGE_ID, "reuse": "frozen-clinical-base"},
            "source_commit": runner.SOURCE_COMMIT,
            "frozen_master_commit": runner.SOURCE_COMMIT,
            "reference_panel_sha256": runner.PANEL_SHA256,
            "inputs": {"real": plan["inputs"]["canonical_manifest_sha256"],
                       "synthetic": "e" * 64},
            "guard": {"max_wall_seconds": 2400, "max_rss_bytes": 4_000_000_000,
                      "cpu_allocation": 2, "exclusive_execution_slot": True,
                      "kernel_enforcement": False, "minimum_free_bytes": 32 * 1024**3},
            "acceptance_effect": "none", "enabled": True,
        }
        report = {
            "schema": "ivanka.assembler-bench.public.v1", "title": "fixture",
            "runs": [{"id": "fixture-real", "cohort": "real",
                      "tools": ["iva", "ivanka"], "roster": [],
                      "tool_labels": {"iva": "IVA", "ivanka": "Ivanka"},
                      "expected_sample_count": 1, "sample_count": 1,
                      "samples": [{"alias": "R001", "score": {},
                                   "seconds": {}, "diagnostics": {},
                                   "failures": [], "outcome": "success"}],
                      "dominance_matrix": {}}],
        }
        merged, joined = display.merge_diagnostic_report(
            report, registry, rows, attested_inputs=mapping)
        self.assertEqual(joined, 1)
        arm = merged["runs"][0]["samples"][0]["diagnostics"][display.TOOL_ID]
        self.assertIsNone(arm["final_contig_count"])


class PilotPlanTests(unittest.TestCase):
    def test_plan_includes_physical_synthetic_and_multitruth(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pcase, _ = make_plan(root / "p", alias="R001", cohort="real")
            scase, _ = make_plan(root / "s", alias="H001", cohort="synthetic")
            plan = ctl.build_pilot_plan(
                physical_cases=[ctl.PilotCase(case=pcase)],
                synthetic_cases=[ctl.PilotCase(case=scase)],
                stamp=STAMP, token=TOKEN)
        self.assertEqual(plan["schema"], ctl.PLAN_SCHEMA)
        self.assertEqual(plan["qualification_claim"], "NONE")
        self.assertTrue(plan["diagnostic_only"])
        self.assertFalse(plan["execution_performed"])
        self.assertEqual(plan["case_count"], 2)
        self.assertFalse(plan["cohorts"]["physical"][0]["multitruth_diagnostic"])
        self.assertTrue(plan["cohorts"]["synthetic"][0]["multitruth_diagnostic"])
        guards = plan["guards"]
        self.assertEqual(guards["reserve_bytes"], 32 * 1024**3)
        self.assertEqual(guards["wall_seconds"], 2400)
        self.assertEqual(guards["rss_limit_bytes"], 4_000_000_000)
        self.assertTrue(guards["exclusive_slot_required"])
        self.assertTrue(guards["no_truth_mounted"])
