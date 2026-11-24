"""Adversarial tests for the fail-closed final physical P0 decision tool."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import final_p0_decision as decision
import independent_frozen_psi_audit as audit


def make_report(deltas=None, *, attested=audit.EXPECTED_CASES, floors=None, readback=True):
    """Build a PR433-shaped report using PR433's own signed-power implementation."""
    if deltas is None:
        deltas = {tool: {"score": [1] * attested,
                         "runtime": [1] * attested}
                  for tool in audit.RIVALS}
    comparators = {}
    for tool in audit.RIVALS:
        axes = deltas[tool]
        score = audit.signed_power(axes["score"])
        runtime = audit.signed_power(axes["runtime"])
        paired = score["paired"]
        comparators[tool] = {
            "paired": paired,
            "unpaired_among_finished": attested - paired,
            "unfinished_cases": audit.EXPECTED_CASES - attested,
            "missing_or_failed_total": audit.EXPECTED_CASES - paired,
            "score": score,
            "runtime": runtime,
        }
    complete = attested == audit.EXPECTED_CASES
    return {
        "schema": audit.SCHEMA,
        "scope": "COMPLETE_COHORT_DIAGNOSTIC" if complete else "EXPLICITLY_PARTIAL",
        "attested_finished_cases": attested,
        "expected_cases": audit.EXPECTED_CASES,
        "observed_quality_floor_failures": floors or {"best_available": 0, "iva": 0},
        "attestation": {"finished_with_both_files": attested, "rejection_reasons": {}},
        "candidate_alignment_recomputed": readback,
        "pinned": {"image_sha256": audit.IMAGE, "manifest_sha256": audit.MANIFEST,
                   "panel_sha256": audit.PANEL},
        "comparators": comparators,
        "full_cohort_eligible": complete and all(row["paired"] == audit.EXPECTED_CASES
                                                 for row in comparators.values()),
        "status": ("COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION" if complete
                   else "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE"),
        "qualification_claim": "NONE",
    }


class FinalDecisionTests(unittest.TestCase):
    def test_full_seven_pass_never_claims_expanded_gate(self):
        result = decision.decide(make_report())
        self.assertEqual(result["decision"], decision.PHYSICAL_FULL_SEVEN_PASS)
        self.assertTrue(result["gates"]["physical_full_seven_pass"])
        self.assertTrue(result["gates"]["original_iva_gate_pass"])
        self.assertFalse(result["gates"]["expanded_464_synthetic_claim"])
        self.assertEqual(result["expanded_claim"], "NONE")
        self.assertEqual(result["qualification_claim"], "NONE")

    def test_incomplete_cohort(self):
        result = decision.decide(make_report(attested=audit.EXPECTED_CASES - 1))
        self.assertEqual(result["decision"], decision.INCOMPLETE_COHORT)
        self.assertFalse(result["cohort"]["complete"])
        self.assertFalse(result["gates"]["physical_full_seven_pass"])

    def test_no_pairs_is_not_a_win(self):
        deltas = make_deltas()
        deltas["abyss"] = {"score": [], "runtime": []}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.NO_PAIRED_EVIDENCE)
        self.assertFalse(result["gates"]["strict_paired_diagnostic_pass"])
        self.assertTrue(any(item["rival"] == "abyss" for item in result["missing_rival_arms"]))

    def test_exact_ties_fail_at_r_zero(self):
        self.assertEqual(audit.signed_power([0, 0])["verdict"], "fails_nonpositive_at_r_zero")
        deltas = make_deltas()
        deltas["iva"] = {"score": [0, 0], "runtime": [1, 1]}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.SIGNED_POWER_FAILURE_AT_R_ZERO)
        self.assertFalse(result["gates"]["original_iva_gate_pass"])
        self.assertEqual(result["signed_power_failures"][0]["rival"], "iva")

    def test_partial_measured_failure_is_not_integrity_or_incomplete(self):
        deltas = make_deltas()
        deltas["abyss"] = {"score": [2, 2, -3], "runtime": [1, 1, 1]}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.SIGNED_POWER_FAILURE_HIGH_R_TAIL)
        self.assertEqual(result["integrity_reasons"], [])
        self.assertTrue(result["cohort"]["complete"])
        self.assertTrue(any(item["state"] == decision.SIGNED_POWER_FAILURE_HIGH_R_TAIL
                            for item in result["signed_power_failures"]))

    def test_interior_failure_state(self):
        interior = [10, -5, -5, -5, 1, 1, 1]
        self.assertEqual(audit.signed_power(interior)["verdict"],
                         "fails_interior_zero_or_negative")
        deltas = make_deltas()
        deltas["velvet"] = {"score": interior, "runtime": [1] * len(interior)}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.SIGNED_POWER_FAILURE_INTERIOR)

    def test_full_measured_failure_reports_all_axes(self):
        deltas = make_deltas()
        deltas["iva"] = {"score": [0, 0], "runtime": [1, 1]}
        deltas["abyss"] = {"score": [2, 2, -3], "runtime": [1, 1, 1]}
        interior = [10, -5, -5, -5, 1, 1, 1]
        deltas["spades"] = {"score": interior, "runtime": [1] * len(interior)}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.SIGNED_POWER_FAILURE_AT_R_ZERO)
        states = {item.get("state") for item in result["signed_power_failures"]}
        self.assertIn(decision.SIGNED_POWER_FAILURE_HIGH_R_TAIL, states)
        self.assertIn(decision.SIGNED_POWER_FAILURE_INTERIOR, states)
        self.assertFalse(result["gates"]["physical_full_seven_pass"])

    def test_complete_198_with_missing_rival_but_iva_gate_passes(self):
        deltas = make_deltas()
        deltas["abyss"] = {"score": [1] * 100, "runtime": [1] * 100}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.ORIGINAL_IVA_GATE_PASS)
        self.assertTrue(result["gates"]["original_iva_gate_pass"])
        self.assertFalse(result["gates"]["physical_full_seven_complete"])
        self.assertFalse(result["gates"]["physical_full_seven_pass"])
        self.assertEqual(result["missing_rival_arms"][0]["rival"], "abyss")

    def test_complete_198_strict_paired_success_without_iva_arm(self):
        deltas = make_deltas()
        deltas["iva"] = {"score": [1] * 100, "runtime": [1] * 100}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.STRICT_PAIRED_SUCCESS_MISSING_ARMS)
        self.assertTrue(result["gates"]["strict_paired_diagnostic_pass"])
        self.assertFalse(result["gates"]["original_iva_gate_pass"])

    def test_per_case_floor_failure(self):
        floors = {"best_available": 1, "iva": 0}
        result = decision.decide(make_report(floors=floors))
        self.assertEqual(result["decision"], decision.PER_CASE_FLOOR_FAILURE)
        self.assertEqual(result["per_case_floor_failures"], floors)

    def test_bad_score_and_readback_evidence_is_integrity_failure(self):
        cases = []
        tampered = make_report(readback=False)
        cases.append((tampered, "exact_score_readback_absent"))
        tampered = make_report()
        tampered["attestation"]["rejection_reasons"] = {"image_drift": 3}
        cases.append((tampered, "attestation_rejections_present"))
        tampered = make_report()
        tampered["pinned"]["panel_sha256"] = "0" * 64
        cases.append((tampered, "pinned_panel_drift"))
        tampered = make_report()
        tampered["comparators"]["iva"]["score"]["verdict"] = "fails_nonpositive_at_r_zero"
        cases.append((tampered, "verdict_proof_mismatch"))
        tampered = make_report()
        tampered["comparators"]["abyss"]["missing_or_failed_total"] = 1
        cases.append((tampered, "missing_arm_count_mismatch"))
        tampered = make_report()
        tampered["attestation"]["finished_with_both_files"] = 197
        cases.append((tampered, "attestation_count_mismatch"))
        for report, reason in cases:
            with self.subTest(reason=reason):
                result = decision.decide(report)
                self.assertEqual(result["decision"], decision.INTEGRITY_FAILURE)
                self.assertIn(reason, result["integrity_reasons"])
                self.assertEqual(result["signed_power_failures"], [])
                self.assertFalse(result["gates"]["physical_full_seven_pass"])

    def test_impossible_partial_counts_rejected(self):
        report = make_report(make_deltas(), attested=audit.EXPECTED_CASES - 1)
        result = decision.decide(report)
        self.assertEqual(result["decision"], decision.INTEGRITY_FAILURE)
        self.assertIn("paired_count_invalid", result["integrity_reasons"])
        report = make_report(attested=1, floors={"best_available": 2, "iva": 0})
        self.assertIn("floor_counts_invalid", decision.decide(report)["integrity_reasons"])

    def test_contradictory_positive_proof_rejected(self):
        report = make_report()
        proof = report["comparators"]["iva"]["score"]["proof"]
        proof["zeros_nonnegative"] = [1.0]
        self.assertIn("positive_proof_contradiction", decision.decide(report)["integrity_reasons"])
        report = make_report()
        proof = report["comparators"]["iva"]["score"]["proof"]
        proof["gains"] = 0
        self.assertIn("proof_counts_invalid", decision.decide(report)["integrity_reasons"])

    def test_iva_gate_remains_independent_of_other_failures(self):
        deltas = make_deltas()
        deltas["abyss"] = {"score": [-1] * 198, "runtime": [1] * 198}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["decision"], decision.SIGNED_POWER_FAILURE_AT_R_ZERO)
        self.assertTrue(result["gates"]["original_iva_gate_pass"])
        self.assertTrue(result["gates"]["physical_full_seven_complete"])
        self.assertFalse(result["gates"]["physical_full_seven_pass"])
        result = decision.decide(make_report(floors={"best_available": 1, "iva": 0}))
        self.assertEqual(result["decision"], decision.PER_CASE_FLOOR_FAILURE)
        self.assertTrue(result["gates"]["original_iva_gate_pass"])

    def test_negative_finite_high_r_limit_is_measured_failure(self):
        deltas = make_deltas()
        deltas["abyss"] = {"score": [0.5, 0.5, -1], "runtime": [1, 1, 1]}
        result = decision.decide(make_report(deltas))
        self.assertEqual(result["integrity_reasons"], [])
        self.assertFalse(result["gates"]["strict_paired_diagnostic_pass"])

    def test_iva_failure_not_duplicated(self):
        deltas = make_deltas()
        deltas["iva"] = {"score": [0, 0], "runtime": [1, 1]}
        result = decision.decide(make_report(deltas))
        self.assertEqual(len(result["signed_power_failures"]), 1)

    def test_integrity_precedes_measured_failure(self):
        report = make_report(readback=False)
        report["comparators"]["iva"] = {
            "paired": 2, "unpaired_among_finished": 196, "unfinished_cases": 0,
            "missing_or_failed_total": 196,
            "score": audit.signed_power([0, 0]),
            "runtime": audit.signed_power([1, 1]),
        }
        report["full_cohort_eligible"] = False
        result = decision.decide(report)
        self.assertEqual(result["decision"], decision.INTEGRITY_FAILURE)
        self.assertEqual(result["signed_power_failures"], [])

    def test_output_contains_no_sample_identifiers(self):
        text = json.dumps(decision.decide(make_report()), sort_keys=True)
        self.assertIn('"contains_sample_identifiers": false', text)
        self.assertNotIn("sample_sha256", text)

    def test_decision_module_has_no_assert_statements(self):
        source = Path(decision.__file__).read_text().splitlines()
        statements = [line for line in source if line.lstrip().startswith("assert ")]
        self.assertEqual(statements, [])

    def test_cli_report_and_self_test(self):
        tool = Path(decision.__file__)
        self_test = subprocess.run([sys.executable, str(tool), "--self-test"],
                                   capture_output=True, text=True, check=True)
        self.assertIn("SELF_TEST_OK", self_test.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "audit.json"
            report_path.write_text(json.dumps(make_report()))
            run = subprocess.run([sys.executable, str(tool), "--report", str(report_path)],
                                 capture_output=True, text=True, check=True)
            self.assertIn(decision.PHYSICAL_FULL_SEVEN_PASS, run.stdout)
            bad_path = Path(tmp) / "bad.json"
            bad_path.write_text(json.dumps(make_report(readback=False)))
            bad = subprocess.run([sys.executable, str(tool), "--report", str(bad_path)],
                                 capture_output=True, text=True, check=True)
            self.assertIn(decision.INTEGRITY_FAILURE, bad.stdout)


def make_deltas():
    return {tool: {"score": [1] * audit.EXPECTED_CASES,
                   "runtime": [1] * audit.EXPECTED_CASES}
            for tool in audit.RIVALS}


if __name__ == "__main__":
    unittest.main()
