"""Fail-closed single-invocation policy for the 198-sample milestone."""
import unittest

from strict_single_invocation import enforce_single_invocation


class SingleInvocationTests(unittest.TestCase):
    def test_clean_complete_invocation_remains_eligible(self):
        report = {"milestone198_pass": True, "milestone198_errors": [],
                  "score_psi": {"positive_all_nonnegative": True}}
        self.assertIs(enforce_single_invocation(report, 0), report)
        self.assertTrue(report["milestone198_pass"])
        self.assertFalse(report["resumed_diagnostic_only"])
        self.assertEqual(report["milestone198_errors"], [])

    def test_one_reused_record_disqualifies_even_all_r_positive(self):
        report = {"milestone198_pass": True, "milestone198_errors": [],
                  "score_psi": {"positive_all_nonnegative": True},
                  "time_psi": {"positive_all_nonnegative": True}}
        enforce_single_invocation(report, 1)
        self.assertFalse(report["milestone198_pass"])
        self.assertTrue(report["resumed_diagnostic_only"])
        self.assertIn("reused_records_not_single_invocation",
                      report["milestone198_errors"])
        self.assertTrue(report["score_psi"]["positive_all_nonnegative"])
        self.assertTrue(report["time_psi"]["positive_all_nonnegative"])

    def test_original_failures_are_preserved(self):
        report = {"milestone198_pass": False,
                  "milestone198_errors": ["sample_count_not_198"]}
        enforce_single_invocation(report, 114)
        self.assertIn("sample_count_not_198", report["milestone198_errors"])
        self.assertIn("reused_records_not_single_invocation",
                      report["milestone198_errors"])

    def test_invalid_reuse_counts_rejected(self):
        for invalid in (-1, False, 1.5, "1", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    enforce_single_invocation({}, invalid)


if __name__ == "__main__":
    unittest.main()
