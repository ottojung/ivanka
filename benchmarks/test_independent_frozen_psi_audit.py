"""Synthetic checks for the independent frozen-original PSI audit.

These tests use invented signed deltas only; no benchmark case, reference,
truth, sample name or clinical output is involved.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

import independent_frozen_psi_audit as audit


class IndependentAuditTests(unittest.TestCase):
    def test_zero_exponent_boundary_is_strict(self):
        self.assertEqual(audit.signed_power([1, -1])["verdict"],
                         "fails_nonpositive_at_r_zero")
        self.assertEqual(audit.signed_power([1, 0, -1])["verdict"],
                         "fails_nonpositive_at_r_zero")

    def test_ties_count_in_denominator(self):
        proof = audit.signed_power([1, 0, 0])["proof"]
        self.assertEqual(proof["ties"], 2)
        self.assertAlmostEqual(proof["psi0"], 1 / 3)
        self.assertEqual(audit.signed_power([1, 0, 0])["verdict"],
                         "dominates_on_observed_pairs")

    def test_all_zero_deltas_are_not_a_pass(self):
        result = audit.signed_power([0, 0])
        self.assertTrue(result["tail"]["all_zero_deltas"])
        self.assertEqual(result["verdict"], "fails_nonpositive_at_r_zero")

    def test_negative_high_r_tail_is_reported(self):
        result = audit.signed_power([2, 2, -3])
        self.assertEqual(result["verdict"], "fails_negative_high_r_tail")
        self.assertEqual(result["tail"]["top_net_count"], -1)
        self.assertEqual(result["proof"]["psi_at_positive_infinity"], "-inf")
        self.assertAlmostEqual(result["tail"]["min_tail_magnitude"], 3.0)

    def test_low_r_negative_majority_recovers_at_high_r(self):
        result = audit.signed_power([125, -1] * 7 + [-1] * 9)
        self.assertEqual(result["verdict"], "fails_nonpositive_at_r_zero")
        self.assertEqual(result["proof"]["psi_at_positive_infinity"], "+inf")

    def test_empty_and_single_sign(self):
        self.assertEqual(audit.signed_power([])["verdict"], "no_paired_successes")
        self.assertEqual(audit.signed_power([-1, 100])["verdict"],
                         "fails_nonpositive_at_r_zero")
        self.assertEqual(audit.signed_power([-1, 100, 100])["verdict"],
                         "dominates_on_observed_pairs")

    def test_missing_arm_never_implies_full_cohort(self):
        paired = {tool: {"paired": audit.EXPECTED_CASES} for tool in audit.RIVALS}
        missing = dict(paired, abyss={"paired": audit.EXPECTED_CASES - 1})
        self.assertTrue(audit.cohort_status(audit.EXPECTED_CASES, paired)[1])
        self.assertFalse(audit.cohort_status(audit.EXPECTED_CASES, missing)[1])
        self.assertEqual(audit.cohort_status(audit.EXPECTED_CASES, missing)[2],
                         "COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION")

    def test_partial_cohort_cannot_be_full_cohort(self):
        paired = {tool: {"paired": audit.EXPECTED_CASES} for tool in audit.RIVALS}
        self.assertEqual(audit.cohort_status(audit.EXPECTED_CASES - 1, paired),
                         (False, False, "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE"))

    def test_checkpoint_copy_cannot_change_metrics_or_status(self):
        original = {"status": "finished", "failed": False,
                    "reference_panel_sha256": "panel",
                    "measurement": {"score": 200, "seconds": 20}}
        copied = {"status": "success", "score": 200, "runtime_seconds": 20}
        self.assertTrue(audit.checkpoint_matches(copied, original, "panel"))
        self.assertFalse(audit.checkpoint_matches(dict(copied, score=201), original, "panel"))
        self.assertFalse(audit.checkpoint_matches(dict(copied, runtime_seconds=19), original, "panel"))
        self.assertFalse(audit.checkpoint_matches(copied, original, "other"))
        failed = dict(original, failed=True, measurement=None)
        self.assertFalse(audit.checkpoint_matches(copied, failed, "panel"))
        self.assertTrue(audit.checkpoint_matches(
            {"status": "failed", "score": None, "runtime_seconds": None}, failed, "panel"))

    def test_candidate_metric_copy_must_match_execution(self):
        score = {"candidate_runtime_seconds": 10, "candidate_peak_rss_bytes": 100,
                 "candidate_conseq_sha256": "conseq"}
        planned = {"original_checkpoint_sha256": "original"}
        receipt = {"source_frozen_manifest_sha256": "manifest", "original_checkpoint_sha256": "original",
                   "final_conseq_sha256": "conseq", "internal_seconds": 10,
                   "sampled_rss_peak_bytes": 100, "exit_code": 0, "violation": None,
                   "original_rival_arm_recomputed": False, "valid_final_max_count": 1}
        self.assertTrue(audit.receipt_matches_metrics(score, receipt, planned, "manifest"))
        self.assertFalse(audit.receipt_matches_metrics(
            dict(score, candidate_runtime_seconds=9), receipt, planned, "manifest"))
        self.assertFalse(audit.receipt_matches_metrics(
            score, dict(receipt, violation="disk-floor"), planned, "manifest"))

    def test_claimed_floor_is_recomputed(self):
        score = {"candidate_score": 89, "original_best_available_rival_score": 100,
                 "original_iva_score": 100, "score_floor_90pct_best_available": True,
                 "score_floor_90pct_iva": True,
                 "original_rivals": {"iva": {"status": "success", "score": 100}}}
        self.assertFalse(audit.recomputed_floors(score))
        self.assertTrue(audit.recomputed_floors(dict(score, candidate_score=90)))

    def test_alignment_readback_detects_score_and_max_count_tampering(self):
        with (patch("project_references.final_max_sequences", return_value=["ACGT"]),
              patch("reference_panel.best_panel_alignment", return_value={"score": 4.0})):
            folder = Path("/unused")
            score = {"candidate_score": 4.0}
            receipt = {"valid_final_max_count": 1}
            references = (("test", "ACGT"),)
            self.assertTrue(audit.alignment_matches(folder, score, receipt, references))
            self.assertFalse(audit.alignment_matches(
                folder, dict(score, candidate_score=5.0), receipt, references))
            self.assertFalse(audit.alignment_matches(
                folder, score, dict(receipt, valid_final_max_count=2), references))

    def test_module_self_test(self):
        self.assertTrue(audit.self_test())


if __name__ == "__main__":
    unittest.main()
