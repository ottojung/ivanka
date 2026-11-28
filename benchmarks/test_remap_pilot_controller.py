import copy
import hashlib
import json
import math
import os
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path

from assembler_bench import guarded_canary_launcher as launcher
from assembler_bench import remap_pilot_controller as ctl
from assembler_bench import remap_runner as runner
from assembler_bench import remap_diagnostic as display
from assembler_bench import remap_guarded_exec as gexec
from assembler_bench import px_ram_semantics
from unittest.mock import patch
from fail_closed_guard import heartbeat as heartbeat_module

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
                "unmount_verified": True,
                "unmount_proof": {
                    "fresh_absence_check": True,
                    "unmount_verified": True,
                    "container_removed": False,
                    "pilot_container_id": "a" * 64,
                },
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

    def test_log_copy_integrity_failure_keeps_explicit_failure_receipt(self):
        def runner_with_drifted_log(plan, output_dir, attempt_dir):
            run = self.fake_runner()(plan, output_dir, attempt_dir)
            log = Path(run["log_paths"]["container.log"])
            run["log_sha256"] = {"container.log": "0" * 64}
            return run

        receipt = ctl.execute_case(
            self.pilot_case, plan=self.plan, preflight_result=self.preflight,
            runner=runner_with_drifted_log, output_dir=self.root / "out-drift",
            attempt_dir=self.root / "att-drift",
            scorer=lambda p, c, o: {
                "schema": ctl.SCORING_SCHEMA, "method": "m", "cohort": "real",
                "score": 321.0, "reference_panel_sha256": "f" * 64,
                "best_reference": "x", "multitruth": None})
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_reason"], "log_integrity_failure")
        self.assertIsNone(receipt["score"])
        self.assertIsNone(receipt["seconds"])
        self.assertIn("log_integrity_failure", receipt["diagnostics"])
        self.assertTrue((self.root / "att-drift" / "receipt.json").is_file())
        retention = json.loads(
            (self.root / "att-drift" / "retention.json").read_text())
        self.assertIn("container.log", retention["log_integrity_failure"])

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


class RealGuardedExecutionTests(unittest.TestCase):
    """Source-only proof that the default execution path is the real guard."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case, self.plan = make_plan(self.root / "real", alias="R001", cohort="real")
        self.pre = ctl.preflight(self.plan, free_bytes=40 * 1024**3, exclusive_slot=True)
        self.manifest = {
            "schema": gexec.BINDING_SCHEMA,
            "manifest_sha256": gexec.ORIGINAL_MANIFEST_SHA256,
            "physical_manifest_sha256": "1" * 64,
            "synthetic_cohort_sha256": "2" * 64,
            "truth_opened": False,
            "cases": [{
                "alias": "R001", "cohort": "real",
                "read_sha256": dict(self.plan["inputs"]["read_sha256"]),
                "source_verified": True,
            }],
        }

    @staticmethod
    def realistic_run(plan, output_dir, attempt_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "conseq.csv").write_text("name,consensus\nA,ACGT\n")
        cid = "a" * 64
        return {
            "schema": gexec.EXECUTION_SCHEMA, "status": "finished",
            "returncode": 0, "wall_seconds": 12.5, "bound_cid": cid,
            "unmount_verified": True,
            "unmount_proof": {"fresh_absence_check": True,
                              "unmount_verified": True,
                              "container_removed": False,
                              "pilot_container_id": cid},
            "original_input_binding": {"alias": plan["alias"],
                                       "source_verified": True},
            "guard_receipt": {"bound_cid": cid, "rss_limit_bytes": 4_000_000_000,
                              "wall_seconds": 2400, "cpu_allocation": 2,
                              "kernel_enforcement": False},
            "resource": {"peak_rss_bytes": 3_000_000_000, "samples": 5,
                         "observation_ended": True, "bound_cid": cid,
                         px_ram_semantics.METHOD_KEY: px_ram_semantics.COMPARABLE_METHOD,
                         px_ram_semantics.VERSION_KEY: px_ram_semantics.COMPARABLE_METHOD_VERSION,
                         px_ram_semantics.SCOPE_KEY: px_ram_semantics.COMPARABLE_SCOPE,
                         "guard_receipt": {
                             "bound_cid": cid,
                             "rss_limit_bytes": 4_000_000_000,
                             "wall_seconds": 2400,
                             "cpu_allocation": 2,
                             "kernel_enforcement": False}},
            "log_paths": {"launcher.stdout.log": str(Path(attempt_dir) / "launcher.stdout.log"),
                          "launcher.stderr.log": str(Path(attempt_dir) / "launcher.stderr.log")},
        }

    def test_default_execute_case_uses_real_guarded_path(self):
        calls = {}
        def fake_real(plan, manifest, **kwargs):
            calls["plan"] = plan
            calls["manifest"] = manifest
            return self.realistic_run(plan, kwargs["output_dir"], kwargs["attempt_dir"])
        with patch.object(gexec, "run_guarded_case", side_effect=fake_real):
            receipt = ctl.execute_case(
                ctl.PilotCase(case=self.case), plan=self.plan,
                preflight_result=self.pre, output_dir=self.root / "o",
                attempt_dir=self.root / "a", original_manifest=self.manifest,
                scorer=lambda p, c, o: {"schema": ctl.SCORING_SCHEMA,
                                        "method": "m", "cohort": "real",
                                        "score": 9.0,
                                        "reference_panel_sha256": runner.PANEL_SHA256,
                                        "best_reference": "x", "multitruth": None})
        self.assertEqual(calls["plan"]["run_id"], self.plan["run_id"])
        self.assertIs(calls["manifest"], self.manifest)
        self.assertEqual(receipt["status"], "measured", receipt.get("failure_reason"))
        self.assertTrue((self.root / "a" / "guarded-execution.json").is_file())

    def test_scoring_requires_unmount_proof(self):
        run = self.realistic_run(self.plan, self.root / "o", self.root / "a")
        run.pop("unmount_proof")
        with patch.object(gexec, "run_guarded_case", return_value=run):
            receipt = ctl.execute_case(
                ctl.PilotCase(case=self.case), plan=self.plan,
                preflight_result=self.pre, output_dir=self.root / "o",
                attempt_dir=self.root / "unmount", original_manifest=self.manifest,
                scorer=lambda *a: self.fail("scorer ran without unmount proof"))
        self.assertEqual(receipt["status"], "failed")
        self.assertIsNone(receipt["score"])

    @staticmethod
    def synthetic_manifest(root: Path, **mutations):
        """Hermetic 198+464 fixture; never contains private host reads."""
        cases = []
        for prefix, count in (("R", 198), ("H", 464)):
            for number in range(1, count + 1):
                alias = f"PX-{prefix}{number:03d}"
                cases.append({
                    "alias": alias,
                    "cohort": "physical" if prefix == "R" else "synthetic",
                    "reads": {
                        mate: {
                            "sha256": hashlib.sha256(
                                f"{alias}:{mate}".encode()).hexdigest(),
                            "bytes": 1024,
                            "source_verified": True,
                        } for mate in ("R1", "R2")
                    },
                })
        doc = {
            "schema": gexec.MANIFEST_SCHEMA,
            "physical_manifest_sha256": "1" * 64,
            "synthetic_cohort_sha256": "2" * 64,
            "counts": {"physical": 198, "synthetic": 464},
            "truth_opened": False,
            "errors": [],
            "cases": cases,
            "elapsed_seconds": 0.0,
        }
        doc.update(mutations)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "synthetic-readback.json"
        data = (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()
        path.write_bytes(data)
        return path, hashlib.sha256(data).hexdigest()

    def test_hermetic_manifest_success_path(self):
        path, sha = self.synthetic_manifest(self.root)
        manifest = gexec.load_original_input_manifest(path, expected_sha=sha)
        self.assertEqual(manifest["schema"], gexec.BINDING_SCHEMA)
        self.assertEqual(manifest["manifest_sha256"], sha)
        self.assertFalse(manifest["truth_opened"])
        self.assertEqual(len(manifest["cases"]), 662)
        aliases = {case["alias"] for case in manifest["cases"]}
        self.assertIn("R001", aliases)
        self.assertIn("H464", aliases)

    def test_manifest_tamper_fails_closed(self):
        for mutation in ({"truth_opened": True},
                         {"counts": {"physical": 1, "synthetic": 1}},
                         {"errors": ["R001"]}):
            path, sha = self.synthetic_manifest(self.root, **mutation)
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    gexec.load_original_input_manifest(path, expected_sha=sha)
        path, sha = self.synthetic_manifest(self.root / "wrong-digest")
        with self.assertRaises(ValueError):
            gexec.load_original_input_manifest(path, expected_sha="f" * 64)
        bad = json.loads(path.read_bytes())
        bad["cases"][0]["reads"]["R1"]["source_verified"] = False
        path.write_bytes((json.dumps(bad, sort_keys=True, indent=2) + "\n").encode())
        with self.assertRaises(ValueError):
            gexec.load_original_input_manifest(path,
                                               expected_sha=hashlib.sha256(path.read_bytes()).hexdigest())

    @unittest.skipUnless(Path(gexec.ORIGINAL_MANIFEST).is_file(),
                         "private host manifest unavailable on public CI")
    def test_real_original_manifest_verifies_read_only(self):
        manifest = gexec.load_original_input_manifest()
        self.assertEqual(manifest["schema"], gexec.BINDING_SCHEMA)
        self.assertEqual(manifest["manifest_sha256"], gexec.ORIGINAL_MANIFEST_SHA256)
        self.assertFalse(manifest["truth_opened"])
        self.assertEqual(len(manifest["cases"]), 662)

    def test_manifest_binding_rejects_read_drift(self):
        bad = copy.deepcopy(self.manifest)
        bad["cases"][0]["read_sha256"]["R1"] = "f" * 64
        with self.assertRaises(ValueError):
            gexec.bind_plan_to_original_manifest(self.plan, bad)

    def test_manifest_loader_rejects_truth_opened_and_digest_drift(self):
        with patch.object(gexec, "load_original_input_manifest",
                          side_effect=ValueError("manifest changed")):
            with self.assertRaises(ValueError):
                gexec.load_original_input_manifest()
        # Real loader verifies the on-disk SHA before any parse.
        with self.assertRaises(ValueError):
            gexec.load_original_input_manifest(path=self.root / "missing.json")

    def test_real_runner_refuses_below_reserve_before_spawn(self):
        def forbidden(*args, **kwargs):
            self.fail("process/spawn invoked below reserve")

        def low_usage(path):
            return SimpleNamespace(free=32 * 1024**3 - 1)

        with patch.object(gexec.lease, "require_clear") as require_clear:
            state = gexec.run_guarded_case(
                self.plan, self.manifest, output_dir=self.root / "below-o",
                attempt_dir=self.root / "below-a", owner="test-owner",
                stop_path=self.root / "STOP", watchdog_ready=lambda: {},
                spawn=forbidden, guard_root=self.root / "below-root",
                disk_path=self.root, disk_usage=low_usage)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["failure_reason"], "reserve_shortfall")
        require_clear.assert_not_called()

    def test_real_guard_integration_disk_refresh_teardown_unmount(self):
        """Drive the REAL p1_harness/watch_bound/lease/heartbeat guard.

        Only low-level seams (CID inspect, /proc snapshot, podman CLI result,
        disk usage) are injected. Lock, STOP, lease, watchdog gate, reserve
        check, CID binding, durable heartbeat, watcher and teardown are real.
        """
        root = self.root / "groot"
        root.mkdir(parents=True)
        owner = "remap-review-owner"
        stop_path = root / "STOP"
        gexec.stop.arm(stop_path, owner)
        cid = "a" * 64
        disk_calls = {"n": 0}

        def usage(path):
            disk_calls["n"] += 1
            return SimpleNamespace(free=40 * 1024**3)

        def watchdog_ready():
            return {"ready": True, "identity_bound": True,
                    "pid_ns": 4242, "starttime": 111}

        record = {"starttime": 111, "pid_ns": 4242, "rss": 3_000_000_000,
                  "cmdline_sha": "c" * 64}
        controller = {"starttime": 999, "pid_ns": 777, "rss": 1024,
                      "cmdline_sha": "d" * 64}

        class FakeProc:
            def __init__(self): self.polls = 0
            def poll(self):
                self.polls += 1
                return 0 if self.polls >= 4 else None

        spawned = {}

        def fake_spawn(plan, cidfile, env, stdout, stderr, groot):
            Path(cidfile).write_text(cid + "\n")
            self.assertNotIn("--denovo", gexec.pinned_plan_argv(plan, cidfile))
            self.assertEqual(env["CONTAINERS_STORAGE_CONF"],
                             str(Path(groot).resolve() / "storage.conf"))
            proc = FakeProc()
            spawned["proc"] = proc
            return proc

        proof = {"cid": cid, "container_removed": True,
                 "fresh_absence_check": True, "kernel_enforcement": False}

        with (patch.object(gexec.binding, "inspect_pid", return_value=4242),
              patch.object(gexec.proc, "snapshot",
                           side_effect=lambda: {4242: record,
                                                os.getpid(): controller}),
              patch.object(gexec.teardown, "stop_cid", return_value=proof) as stopper,
              patch.object(gexec.natural_exit, "wait_and_attest",
                           return_value={"cid": cid, "launcher_result": 0}),
              patch.object(gexec.pilot, "ROOT", root),
              patch.object(gexec.pilot, "STORE", str(root / "store")),
              patch.object(gexec.pilot, "command",
                           side_effect=lambda argv, env: "" if argv[1] == "ps"
                           else str(root / "store"))):
            state = gexec.run_guarded_case(
                self.plan, self.manifest, output_dir=root / "out",
                attempt_dir=root / "attempt", owner=owner, stop_path=stop_path,
                watchdog_ready=watchdog_ready, spawn=fake_spawn,
                guard_root=root, disk_path=root, disk_usage=usage,
                sleep=lambda seconds: None)

        self.assertEqual(state["status"], "finished", str(state))
        self.assertTrue(state["unmount_verified"])
        self.assertGreater(disk_calls["n"], 0, "no real disk reserve check")
        self.assertGreaterEqual(state["resource"]["samples"], 1)
        self.assertEqual(state["resource"]["peak_rss_bytes"], 3_000_000_000)
        self.assertEqual(state["resource"][px_ram_semantics.SCOPE_KEY],
                         "whole_container_process_tree")
        self.assertEqual(state["guard_receipt"]["bound_cid"], cid)
        stopper.assert_called()
        self.assertFalse(stop_path.exists(), "STOP not retired after proof")
        heartbeat_schema = heartbeat_module.SCHEMA
        heartbeats = [p for p in root.glob("*.json")
                      if '"schema": "' + heartbeat_schema + '"' in p.read_text()]
        self.assertTrue(heartbeats, "no durable controller heartbeat")
        self.assertEqual(state["harness_outcome"], "completed")

    def test_unmount_failure_forbids_scoring(self):
        root = self.root / "unmount-guard"
        root.mkdir(parents=True)
        owner = "remap-unmount-owner"
        stop_path = root / "STOP"
        gexec.stop.arm(stop_path, owner)
        cid = "a" * 64
        proof = {"cid": cid, "container_removed": True,
                 "fresh_absence_check": True}

        class FakeProc:
            def poll(self): return 0

        def fake_spawn(plan, cidfile, env, stdout, stderr, groot):
            Path(cidfile).write_text(cid + "\n")
            return FakeProc()

        record = {"starttime": 111, "pid_ns": 4242, "rss": 3_000_000_000,
                  "cmdline_sha": "c" * 64}
        controller = {"starttime": 999, "pid_ns": 777, "rss": 1024,
                      "cmdline_sha": "d" * 64}

        with (patch.object(gexec.binding, "inspect_pid", return_value=4242),
              patch.object(gexec.proc, "snapshot",
                           side_effect=lambda: {4242: record,
                                                os.getpid(): controller}),
              patch.object(gexec.teardown, "stop_cid", return_value=proof),
              patch.object(gexec.natural_exit, "wait_and_attest",
                           return_value={"cid": cid, "launcher_result": 0}),
              patch.object(gexec.pilot, "prove_pilot_absent",
                           return_value={"fresh_absence_check": False})):
            run = gexec.run_guarded_case(
                self.plan, self.manifest, output_dir=root / "out",
                attempt_dir=root / "attempt", owner=owner, stop_path=stop_path,
                watchdog_ready=lambda: {"ready": True, "identity_bound": True,
                                        "pid_ns": 4242, "starttime": 111},
                spawn=fake_spawn, guard_root=root, disk_path=root,
                disk_usage=lambda p: SimpleNamespace(free=40 * 1024**3),
                sleep=lambda seconds: None)
        self.assertEqual(run["status"], "failed")
        self.assertIn("unmount_unverified", str(run))
        with patch.object(gexec, "run_guarded_case", return_value=run):
            receipt = ctl.execute_case(
                ctl.PilotCase(case=self.case), plan=self.plan,
                preflight_result=self.pre, output_dir=root / "o2",
                attempt_dir=root / "a2", original_manifest=self.manifest,
                scorer=lambda *a: self.fail("scorer ran without unmount"))
        self.assertEqual(receipt["status"], "failed")
        self.assertIsNone(receipt["score"])


class LogDrainAndRetentionTests(unittest.TestCase):
    """Failed pre-bind launches must hash drained logs, never racing bytes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case, self.plan = make_plan(self.root / "real", alias="R001",
                                          cohort="real")
        self.manifest = {
            "schema": gexec.BINDING_SCHEMA,
            "manifest_sha256": gexec.ORIGINAL_MANIFEST_SHA256,
            "physical_manifest_sha256": "1" * 64,
            "synthetic_cohort_sha256": "2" * 64,
            "truth_opened": False,
            "cases": [{"alias": "R001", "cohort": "real",
                       "read_sha256": dict(self.plan["inputs"]["read_sha256"]),
                       "source_verified": True}],
        }

    def test_guard_hashes_logs_only_after_child_exit(self):
        attempt = self.root / "attempt"
        attempt.mkdir()

        def spawn(plan, cidfile, env, stdout, stderr, groot):
            return subprocess.Popen(
                ["/bin/sh", "-c", "printf late >&2"],
                stdout=open(stdout, "wb"), stderr=open(stderr, "wb"),
                start_new_session=True)

        class Harness:
            class ExclusiveLock:
                def __init__(self, *args, **kwargs):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            @staticmethod
            def run_prospective(**kwargs):
                kwargs["spawn"](attempt / "cid", kwargs["env"])
                raise RuntimeError("early-guard-stop")

        usage = lambda target: SimpleNamespace(free=40 * 1024**3)
        state = gexec.run_guarded_case(
            self.plan, self.manifest,
            output_dir=self.root / "output", attempt_dir=attempt,
            owner="operator-test",
            stop_path=self.root / "STOP", watchdog_ready=lambda: {
                "ready": True, "pid_ns": 1, "starttime": 1},
            guard_root=self.root, disk_path=self.root,
            spawn=spawn, harness=Harness(), disk_usage=usage)
        self.assertTrue(state["launcher_exited"])
        self.assertEqual(state["log_sha256"]["launcher.stderr.log"],
                         hashlib.sha256(b"late").hexdigest())

    def test_retention_refuses_copied_log_hash_mismatch(self):
        attempt = self.root / "attempt"
        attempt.mkdir()
        source = self.root / "launcher.stderr.log"
        source.write_bytes(b"original bytes")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = ctl.retain_case_artifacts(
            attempt_dir=attempt, receipt={"schema": "test"},
            logs={"launcher.stderr.log": str(source)},
            expected_logs={"launcher.stderr.log": digest})
        self.assertEqual(manifest["logs"]["launcher.stderr.log"], digest)
        (attempt / "logs" / "launcher.stderr.log").unlink()
        altered = ctl.retain_case_artifacts(
            attempt_dir=attempt, receipt={"schema": "test"},
            logs={"launcher.stderr.log": str(source)},
            expected_logs={"launcher.stderr.log": "0" * 64})
        self.assertEqual(
            altered["log_integrity_failure"]["launcher.stderr.log"],
            {"source_sha256": "0" * 64, "copy_sha256": digest})
        self.assertTrue((attempt / "receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()
