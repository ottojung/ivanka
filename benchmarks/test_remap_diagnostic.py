"""Opt-in reference-based remap registry: isolation, readback and display data.

These tests use tiny fabricated *public fixtures* only. They never read a
frozen result, run MiCall, or claim benchmark evidence. The point is to prove
that diagnostic rows are honest about missingness and cannot move a private
decision, whether they are absent, present, failed or extreme outliers.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import final_p0_decision as decision
import independent_frozen_psi_audit as audit
import psi_acceptance
from assembler_bench import remap_diagnostic as remap
from assembler_bench.public_validation import check_matrix, is_hash
from assembler_bench.public_psi import public_matrix
from assembler_bench.public_vocabulary import find_tokens
from assembler_bench.px_ram_semantics import (
    COMPARABLE_KEY, COMPARABLE_METHOD, COMPARABLE_METHOD_VERSION,
    COMPARABLE_SCOPE, LAUNCHER_DIAGNOSTIC, METHOD_KEY, SCOPE_KEY,
    VERSION_KEY)


def make_registry(**overrides):
    value = {
        "schema": remap.REGISTRY_SCHEMA,
        "tool_id": remap.TOOL_ID,
        "label": remap.LABEL,
        "method_kind": remap.METHOD_KIND,
        "de_novo": False,
        "invocation": ("micall analyze sample --all_projects --keep_scratch "
                       "(ordinary reference-based mode without the de-novo flag)"),
        "image": {"sha256": "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad",
                  "reuse": "frozen-clinical-base"},
        "source_commit": "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
        "frozen_master_commit": "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
        "reference_panel_sha256": "c" * 64,
        "inputs": {"real": "d" * 64, "synthetic": "e" * 64},
        "guard": {
            "max_wall_seconds": 2400,
            "max_rss_bytes": 4_000_000_000,
            "cpu_allocation": 2,
            "exclusive_execution_slot": True,
            "kernel_enforcement": False,
            "minimum_free_bytes": 32 * 1024 ** 3,
        },
        "acceptance_effect": "none",
        "enabled": True,
    }
    value.update(overrides)
    return value


def make_case(alias="R001", *, status="measured", score=100.5, seconds=12.5,
              diagnostics=None, unavailable=None, **extra):
    value = {
        "alias": alias,
        "status": status,
        "score": score,
        "seconds": seconds,
        "reference_panel_sha256": "c" * 64,
        "canonical_manifest_sha256": "d" * 64 if alias.startswith("R") else "e" * 64,
        "paired_input_sha256": "f" * 64,
        "read_sha256": {"R1": "2" * 64, "R2": "3" * 64},
        "receipt_sha256": "9" * 64,
        "diagnostics": diagnostics if diagnostics is not None else {},
        "unavailable": unavailable or [],
    }
    if status != "measured":
        value["score"] = None
        value["seconds"] = None
        value["failure_reason"] = "recoverable container failure"
    value.update(extra)
    return value


def make_attested_inputs(cases, cohort="real"):
    return {c["alias"]: {
        "alias": c["alias"], "cohort": cohort,
        "canonical_manifest_sha256": c["canonical_manifest_sha256"],
        "read_sha256": c.get("read_sha256", {"R1": "2"*64, "R2": "3"*64}),
        "paired_input_sha256": c.get("paired_input_sha256"),
    } for c in cases}


def make_rows(cases=None, *, cohort="real"):
    cases = cases if cases is not None else [make_case()]
    return {
        "schema": remap.ROWS_SCHEMA,
        "tool_id": remap.TOOL_ID,
        "method_kind": remap.METHOD_KIND,
        "mode": remap.METHOD_KIND,
        "denovo": False,
        "run_id": "remap-real-diagnostic-fixture",
        "image_sha256": ("da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"),
        "frozen_master_commit": "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
        "invocation_sha256": "1" * 64,
        "cohort": cohort,
        "cases": cases,
    }


def make_public_report():
    return {
        "schema": "ivanka.assembler-bench.public.v1",
        "title": "fixture",
        "runs": [{
            "id": "fixture-real",
            "cohort": "real",
            "date": "2026-11-26",
            "tools": ["iva", "ivanka"],
            "roster": [
                {"id": tool, "name": tool.upper(), "status": "measured",
                 "provenance": {}, "cases": []}
                for tool in ("iva", "ivanka")
            ],
            "tool_labels": {"iva": "IVA", "ivanka": "Ivanka"},
            "status": "incomplete",
            "expected_sample_count": 3,
            "sample_count": 3,
            "psi": {"alignment": {"psi1": 1.0}},
            "samples": [
                {"alias": f"R{n:03d}",
                 "score": {"iva": 10.0 + n, "ivanka": 11.0 + n},
                 "seconds": {"iva": 5.0 + n, "ivanka": 4.0 + n},
                 "diagnostics": {}, "failures": [], "outcome": "success"}
                for n in range(1, 4)
            ],
            "dominance_matrix": {},
        }],
    }


def make_audit_report():
    comparators = {}
    for tool in audit.RIVALS:
        evidence = audit.signed_power([1] * audit.EXPECTED_CASES)
        comparators[tool] = {
            "paired": audit.EXPECTED_CASES,
            "unpaired_among_finished": 0,
            "unfinished_cases": 0,
            "missing_or_failed_total": 0,
            "score": evidence,
            "runtime": evidence,
        }
    return {
        "schema": audit.SCHEMA,
        "scope": "COMPLETE_COHORT_DIAGNOSTIC",
        "status": "COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION",
        "attested_finished_cases": audit.EXPECTED_CASES,
        "expected_cases": audit.EXPECTED_CASES,
        "observed_quality_floor_failures": {"best_available": 0, "iva": 0},
        "attestation": {"finished_with_both_files": audit.EXPECTED_CASES,
                        "rejection_reasons": {}},
        "candidate_alignment_recomputed": True,
        "pinned": {"image_sha256": audit.IMAGE,
                   "manifest_sha256": audit.MANIFEST,
                   "panel_sha256": audit.PANEL},
        "comparators": comparators,
        "full_cohort_eligible": True,
        "qualification_claim": "NONE",
    }


class RegistryContractTests(unittest.TestCase):
    def test_registry_is_strictly_opt_in_and_reference_based(self):
        registry = make_registry(enabled=False)
        self.assertEqual(remap.validate_registry(registry)["enabled"], False)
        for change in ({"de_novo": True},
                       {"method_kind": "de-novo"},
                       {"invocation": "micall analyze sample --denovo"},
                       {"label": "MiCall Remap (de novo)"},
                       {"acceptance_effect": "strongest-rival"},
                       {"enabled": "yes"}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    remap.validate_registry(make_registry(**change))
        guard = dict(make_registry()["guard"], max_rss_bytes=5_000_000_000)
        with self.assertRaises(ValueError):
            remap.validate_registry(make_registry(guard=guard))

    def test_registry_identifies_shared_frozen_image_honestly(self):
        registry = remap.validate_registry(make_registry())
        self.assertEqual(registry["image"]["reuse"], "frozen-clinical-base")
        self.assertTrue(is_hash(registry["image"]["sha256"]))
        with self.assertRaises(ValueError):
            remap.validate_registry(make_registry(
                image={"sha256": "b" * 64, "reuse": "new-build"}))

    def test_rival_roster_mirror_matches_the_private_gate(self):
        self.assertEqual(remap.QUALIFICATION_RIVALS, audit.RIVALS)


class RowContractTests(unittest.TestCase):
    def test_missing_metrics_are_null_and_never_zero(self):
        case = make_case(diagnostics={
            "exact_coverage_breadth_ge_1": 0.93,
            "aligned_read_bases": 1000,
            "final_contig_count": None,
            "nuc_detail_rows": None,
            "amino_detail_rows": None,
            "conseq_region_rows": None,
            "unstitched_contig_count": None,
        }, unavailable=["final_contig_count", "nuc_detail_rows",
                        "amino_detail_rows", "conseq_region_rows",
                        "unstitched_contig_count"])
        remap.validate_rows(make_rows([case]))
        for key in case["unavailable"]:
            self.assertIsNone(case["diagnostics"][key])
        self.assertEqual(case["diagnostics"]["exact_coverage_breadth_ge_1"], 0.93)
        forged = make_case(diagnostics={"nuc_detail_rows": 0.0})
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([forged]))

    def test_launcher_rss_is_never_a_comparable_peak(self):
        case = make_case(diagnostics={
            COMPARABLE_KEY: 400.0,
            METHOD_KEY: "launcher_process_group_rss",
            SCOPE_KEY: "launcher_process_group",
            LAUNCHER_DIAGNOSTIC: 400.0,
        })
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([case]))
        honest = make_case(diagnostics={
            COMPARABLE_KEY: None,
            METHOD_KEY: "launcher_process_group_rss",
            SCOPE_KEY: "launcher_process_group",
            LAUNCHER_DIAGNOSTIC: 400.0,
        })
        remap.validate_rows(make_rows([honest]))
        attested_case = make_case(diagnostics={
            COMPARABLE_KEY: 3100.25,
            METHOD_KEY: COMPARABLE_METHOD,
            VERSION_KEY: COMPARABLE_METHOD_VERSION,
            SCOPE_KEY: COMPARABLE_SCOPE,
        })
        remap.validate_rows(make_rows([attested_case]))

    def test_truth_and_denovo_contigs_are_rejected(self):
        for case in (make_case(truth="HXB2"),
                     make_case(unstitched_contigs="present")):
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    remap.validate_rows(make_rows([case]))

    def test_failed_rows_keep_evidence_without_inventing_scores(self):
        case = make_case(status="failed", diagnostics={"aligned_read_bases": None},
                         unavailable=["aligned_read_bases"])
        remap.validate_rows(make_rows([case]))
        forged = make_case(status="failed")
        forged["score"] = 5.0
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([forged]))


class QualificationInvarianceTests(unittest.TestCase):
    def test_absent_present_failed_and_outlier_rows_are_inert(self):
        base = make_audit_report()
        canonical = lambda value: json.dumps(value, sort_keys=True,
                                             separators=(",", ":"))
        baseline = decision.decide(base)
        self.assertEqual(baseline["decision"], decision.PHYSICAL_FULL_SEVEN_PASS)
        variants = {
            "absent": [],
            "present-success": [make_case()],
            "present-failed": [make_case(status="failed")],
            "present-outlier": [make_case(score=1e9, seconds=0.001)],
        }
        for name, cases in variants.items():
            with self.subTest(variant=name):
                candidate = copy.deepcopy(base)
                candidate["comparators"][remap.TOOL_ID] = {
                    "paired": len(cases), "score": {"verdict": "observed"},
                    "runtime": {"verdict": "observed"},
                }
                view = remap.qualification_view(candidate)
                result = decision.decide(view)
                # Byte-identical decision object, not merely the same state.
                self.assertEqual(canonical(result), canonical(baseline))
                self.assertEqual(sorted(view["comparators"]), sorted(audit.RIVALS))
                self.assertEqual(result["gates"], baseline["gates"])
                self.assertEqual(result["per_case_floor_failures"],
                                 {"best_available": 0, "iva": 0})
                self.assertEqual(result["missing_rival_arms"], [])
                self.assertEqual(result["signed_power_failures"], [])
                self.assertEqual(result["qualification_claim"], "NONE")
                self.assertEqual(result["cohort"]["expected_cases"], 198)
        # Without the isolation boundary the extra roster entry is rejected:
        # isolation is an explicit contract, not an accident of the gate.
        with_remap = copy.deepcopy(base)
        with_remap["comparators"][remap.TOOL_ID] = {}
        self.assertEqual(decision.decide(with_remap)["decision"],
                         decision.INTEGRITY_FAILURE)

    def test_denominator_and_private_gate_sources_are_unchanged(self):
        report = make_public_report()
        report["runs"][0]["expected_sample_count"] = 198
        report["runs"].append(copy.deepcopy(report["runs"][0]))
        report["runs"][1]["cohort"] = "synthetic"
        report["runs"][1]["expected_sample_count"] = 464
        merged, _ = remap.merge_diagnostic_report(
            report, make_registry(), make_rows(),
            attested_inputs=make_attested_inputs(make_rows()['cases']))
        view = remap.qualification_view(merged)
        self.assertEqual(sum(run["expected_sample_count"]
                             for run in view["runs"]), 662)
        # No registry token may enter the pinned private decision sources.
        root = Path(__file__).resolve().parent
        for name in ("final_p0_decision.py", "qualify_updated_micall.py",
                     "expanded/gate.py"):
            source = (root / name).read_text()
            self.assertNotIn(remap.TOOL_ID, source)
            self.assertNotIn("reference-based", source.lower())

    def test_psi_denominator_and_required_rivals_are_unchanged(self):
        values = [1.0, 2.0, -1.0]
        baseline = psi_acceptance.summarize(values)
        padded = [{"tool": "iva", "delta": 1.0},
                  {"tool": remap.TOOL_ID, "delta": -1000.0},
                  {"tool": remap.TOOL_ID, "delta": 1000.0}]
        kept = [item["delta"] for item in remap.qualification_view(padded)]
        self.assertEqual(kept, [1.0])
        self.assertEqual(psi_acceptance.summarize(kept)["psi0"], 1.0)
        self.assertEqual(baseline["positive_all_nonnegative"], True)

    def test_public_report_view_restores_original_roster(self):
        rows = make_rows()
        merged, joined = remap.merge_diagnostic_report(
            make_public_report(), make_registry(), rows,
            attested_inputs=make_attested_inputs(rows['cases']))
        self.assertGreater(joined, 0)
        stripped = remap.qualification_view(merged)
        original = make_public_report()
        self.assertEqual(stripped["runs"][0]["tools"], original["runs"][0]["tools"])
        self.assertEqual(stripped["runs"][0]["dominance_matrix"],
                         public_matrix(original["runs"][0]))
        self.assertNotIn(remap.TOOL_ID, json.dumps(stripped))


class PublicDisplayMergeTests(unittest.TestCase):
    def test_opt_in_off_leaves_report_untouched(self):
        report = make_public_report()
        merged, joined = remap.merge_diagnostic_report(
            report, make_registry(enabled=False), make_rows(), attested_inputs=make_attested_inputs((make_rows())["cases"], (make_rows()).get("cohort","real")))
        self.assertEqual(joined, 0)
        self.assertEqual(merged, report)

    def test_merge_is_additive_and_does_not_mutate_inputs(self):
        report, registry, rows = make_public_report(), make_registry(), make_rows()
        before = copy.deepcopy((report, registry, rows))
        merged, joined = remap.merge_diagnostic_report(report, registry, rows, attested_inputs=make_attested_inputs(rows["cases"], rows.get("cohort","real")))
        self.assertEqual((report, registry, rows), before)
        self.assertEqual(joined, 1)
        run = merged["runs"][0]
        self.assertIn(remap.TOOL_ID, run["tools"])
        self.assertEqual([item["id"] for item in run["roster"]], run["tools"])
        self.assertEqual(run["tool_labels"][remap.TOOL_ID], remap.LABEL)
        self.assertEqual(run["tool_modes"][remap.TOOL_ID]["kind"],
                         remap.METHOD_KIND)
        self.assertEqual(run["tool_modes"][remap.TOOL_ID]["de_novo"], False)
        self.assertEqual(merged["runs"][0]["psi"], report["runs"][0]["psi"])
        self.assertEqual(check_matrix(run), len(run["tools"]))
        self.assertEqual(find_tokens(json.dumps(merged)), [])

    def test_unavailable_metrics_stay_na_not_zero(self):
        cases = [make_case(diagnostics={
            "final_contig_count": None,
            "final_contig_total_bases": None,
            "exact_coverage_breadth_ge_1": 0.88,
        }, unavailable=["final_contig_count", "final_contig_total_bases"])]
        merged, _ = remap.merge_diagnostic_report(
            make_public_report(), make_registry(), make_rows(cases), attested_inputs=make_attested_inputs((make_rows(cases))["cases"], (make_rows(cases)).get("cohort","real")))
        arm = merged["runs"][0]["samples"][0]["diagnostics"][remap.TOOL_ID]
        self.assertIsNone(arm["final_contig_count"])
        self.assertIsNone(arm["final_contig_total_bases"])
        self.assertEqual(arm["unavailable_reasons"]["final_contig_count"],
                         remap.NOT_APPLICABLE)
        self.assertEqual(arm["exact_coverage_breadth_ge_1"], 0.88)

    def test_failed_case_is_published_as_failure(self):
        merged, _ = remap.merge_diagnostic_report(
            make_public_report(), make_registry(),
            make_rows([make_case(status="failed")]),
            attested_inputs=make_attested_inputs([make_case(status="failed")]))
        sample = merged["runs"][0]["samples"][0]
        self.assertIn(remap.TOOL_ID, sample["failures"])
        self.assertIsNone(sample["score"][remap.TOOL_ID])

    def test_distinct_run_identity_is_recorded_not_reused(self):
        merged, _ = remap.merge_diagnostic_report(
            make_public_report(), make_registry(), make_rows(),
            attested_inputs=make_attested_inputs(make_rows()['cases']))
        method = merged["runs"][0]["diagnostic_methods"][0]
        self.assertEqual(method["run_id"], "remap-real-diagnostic-fixture")
        self.assertNotEqual(method["run_id"], merged["runs"][0]["id"])
        self.assertEqual(method["method"], remap.METHOD_KIND)


class StagedReadbackTests(unittest.TestCase):
    def test_registry_rows_roundtrip_is_byte_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry.json").write_text(json.dumps(make_registry(),
                                                           sort_keys=True))
            (root / "rows.json").write_text(json.dumps(make_rows(), sort_keys=True))
            registry = remap.validate_registry(
                json.loads((root / "registry.json").read_text()))
            rows = remap.validate_rows(
                json.loads((root / "rows.json").read_text()))
            first, _ = remap.merge_diagnostic_report(
                make_public_report(), registry, rows, attested_inputs=make_attested_inputs(rows["cases"], rows.get("cohort","real")))
            second, _ = remap.merge_diagnostic_report(
                make_public_report(), registry, rows, attested_inputs=make_attested_inputs(rows["cases"], rows.get("cohort","real")))
            encoded = lambda doc: json.dumps(doc, sort_keys=True, separators=(",", ":"))
            self.assertEqual(encoded(first), encoded(second))

    def test_rows_for_another_cohort_cannot_join_this_run(self):
        case = make_case(alias="H001")
        case["canonical_manifest_sha256"] = "e" * 64
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([case], cohort="real"))
        rows = make_rows([case], cohort="synthetic")
        merged, joined = remap.merge_diagnostic_report(
            make_public_report(), make_registry(), rows,
            attested_inputs=make_attested_inputs(rows["cases"], "synthetic"))
        self.assertEqual(joined, 0)
        self.assertNotIn(remap.TOOL_ID, merged["runs"][0]["tools"])


class RunnerRowShapeTests(unittest.TestCase):
    """Non-skipping contract test against the runner's emitted row shape."""

    RUNNER_ROW_KEYS = frozenset((
        "schema", "tool_id", "method_kind", "mode", "denovo",
        "image_sha256", "frozen_master_commit", "invocation_sha256",
        "run_id", "cohort", "cases",
    ))
    RUNNER_CASE_KEYS = frozenset((
        "alias", "status", "score", "seconds", "reference_panel_sha256",
        "canonical_manifest_sha256", "read_sha256", "paired_input_sha256",
        "receipt_sha256", "diagnostics", "unavailable",
        "unstitched_contigs", "failure_reason",
    ))

    def make_runner_rows(self):
        rows = make_rows([make_case(
            diagnostics={"aligned_read_bases": 1000,
                         "final_contig_count": None,
                         "unstitched_contig_count": None},
            unavailable=["final_contig_count", "unstitched_contig_count"],
            unstitched_contigs="not-applicable",
        )])
        # The runner always serializes the terminal failure reason, including
        # an empty one for a successful attempt.
        rows["cases"][0]["failure_reason"] = None
        return rows

    def test_runner_emitted_shape_roundtrips_without_relaxing_validation(self):
        rows = self.make_runner_rows()
        self.assertEqual(set(rows), self.RUNNER_ROW_KEYS)
        self.assertEqual(set(rows["cases"][0]), self.RUNNER_CASE_KEYS)
        validated = remap.validate_rows(rows)
        merged, joined = remap.merge_diagnostic_report(
            make_public_report(), make_registry(), validated, attested_inputs=make_attested_inputs((validated).get("cases",[]), (validated).get("cohort","real")))
        self.assertEqual(joined, 1)
        arm = merged["runs"][0]["samples"][0]["diagnostics"][remap.TOOL_ID]
        self.assertIsNone(arm["final_contig_count"])
        self.assertEqual(arm["unavailable_reasons"]["final_contig_count"],
                         remap.NOT_APPLICABLE)
        self.assertEqual(arm["aligned_read_bases"], 1000)

    def test_missing_runner_identity_fields_are_rejected(self):
        rows = self.make_runner_rows()
        for key in ("mode", "denovo", "image_sha256",
                    "frozen_master_commit", "invocation_sha256"):
            with self.subTest(key=key):
                candidate = copy.deepcopy(rows)
                candidate.pop(key)
                with self.assertRaises(ValueError):
                    remap.validate_rows(candidate)


class AdversarialMergeTests(unittest.TestCase):
    def test_requires_independent_attested_input_mapping(self):
        rows = make_rows()
        with self.assertRaises(ValueError):
            remap.merge_diagnostic_report(make_public_report(), make_registry(), rows)
        bad = make_attested_inputs(rows["cases"])
        bad["R001"]["read_sha256"] = {"R1": "0" * 64, "R2": "3" * 64}
        with self.assertRaises(ValueError):
            remap.merge_diagnostic_report(make_public_report(), make_registry(), rows,
                                          attested_inputs=bad)

    def test_alias_prefix_must_match_rows_cohort(self):
        case = make_case(alias="R001")
        case["canonical_manifest_sha256"] = "e" * 64
        rows = make_rows([case], cohort="synthetic")
        with self.assertRaises(ValueError):
            remap.validate_rows(rows)

    def test_cross_cohort_alias_cannot_be_merged(self):
        rows = make_rows([make_case(alias="R001")], cohort="real")
        report = make_public_report()
        report["runs"][0]["cohort"] = "synthetic"
        report["runs"][0]["samples"] = [{
            "alias": "H001", "score": {"iva": 1.0}, "seconds": {"iva": 1.0},
            "diagnostics": {}, "failures": [], "outcome": "success",
        }]
        merged, joined = remap.merge_diagnostic_report(
            report, make_registry(), rows, attested_inputs=make_attested_inputs(rows["cases"]))
        self.assertEqual(joined, 0)
        self.assertNotIn(remap.TOOL_ID, merged["runs"][0]["tools"])

    def test_duplicate_roster_and_method_rows_are_not_duplicated(self):
        rows = make_rows()
        report = make_public_report()
        att = make_attested_inputs(rows["cases"])
        merged, joined = remap.merge_diagnostic_report(report, make_registry(), rows, attested_inputs=att)
        merged2, joined2 = remap.merge_diagnostic_report(merged, make_registry(), rows, attested_inputs=att)
        self.assertEqual(joined, 1)
        self.assertEqual(joined2, 0)
        run = merged2["runs"][0]
        self.assertEqual(sum(1 for i in run["roster"] if i["id"] == remap.TOOL_ID), 1)
        self.assertEqual(sum(1 for m in run.get("diagnostic_methods", []) if m.get("run_id") == rows["run_id"]), 1)

    def test_combined_cohort_real_and_synthetic_rows_do_not_duplicate_roster(self):
        report = make_public_report()
        report["runs"][0]["cohort"] = "combined"
        report["runs"][0]["id"] = "fixture-combined"
        report["runs"][0]["samples"] = [
            {"alias": "R-R001", "score": {"iva": 10.0}, "seconds": {"iva": 5.0},
             "diagnostics": {}, "failures": [], "outcome": "success"},
            {"alias": "S-H001", "score": {"iva": 20.0}, "seconds": {"iva": 6.0},
             "diagnostics": {}, "failures": [], "outcome": "success"},
        ]
        real_case = make_case(alias="R001")
        real_rows = make_rows([real_case], cohort="real")
        syn_case = make_case(alias="H001")
        syn_case["canonical_manifest_sha256"] = "e" * 64
        syn_rows = make_rows([syn_case], cohort="synthetic")
        syn_rows["run_id"] = "remap-synthetic-diagnostic-fixture"
        merged, j1 = remap.merge_diagnostic_report(report, make_registry(), real_rows,
                                                   attested_inputs=make_attested_inputs(real_rows["cases"], "real"))
        merged, j2 = remap.merge_diagnostic_report(merged, make_registry(), syn_rows,
                                                   attested_inputs=make_attested_inputs(syn_rows["cases"], "synthetic"))
        self.assertEqual((j1, j2), (1, 1))
        run = merged["runs"][0]
        self.assertEqual(sum(1 for i in run["roster"] if i["id"] == remap.TOOL_ID), 1)
        ids = [m["run_id"] for m in run.get("diagnostic_methods", []) if m["id"] == remap.TOOL_ID]
        self.assertEqual(sorted(ids), ["remap-real-diagnostic-fixture", "remap-synthetic-diagnostic-fixture"])
        note = run["tool_notes"][remap.TOOL_ID]
        self.assertIn("physical scoring against the ordinary frozen reference panel", note)
        self.assertIn("synthetic hidden-truth post-hoc scoring", note)

    def test_measured_seconds_must_be_positive_and_bounded(self):
        bad = make_case(seconds=0.0)
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([bad]))
        bad = make_case(seconds=2401.0)
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([bad]))
        bad = make_case(seconds=float("nan"))
        with self.assertRaises(ValueError):
            remap.validate_rows(make_rows([bad]))

    def test_receipt_sha256_alone_does_not_bind_input(self):
        rows = make_rows()
        att = make_attested_inputs(rows["cases"])
        att["R001"]["read_sha256"] = {"R1": "4" * 64, "R2": "5" * 64}
        with self.assertRaises(ValueError):
            remap.merge_diagnostic_report(make_public_report(), make_registry(), rows, attested_inputs=att)


if __name__ == "__main__":
    unittest.main()

