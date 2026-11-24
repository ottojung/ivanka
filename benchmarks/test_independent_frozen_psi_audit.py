"""Synthetic checks for the independent frozen-original PSI audit.

These tests use invented signed deltas only; no benchmark case, reference,
truth, sample name or clinical output is involved.
"""

import unittest

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

    def test_module_self_test(self):
        self.assertTrue(audit.self_test())


if __name__ == "__main__":
    unittest.main()
