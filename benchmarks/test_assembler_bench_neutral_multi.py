"""Regression tests: every assembler's evidence is checked independently."""
import copy
import unittest

from assembler_bench.public_validation import check_joined_measurements


class JoinedMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "assemblers": [
                {"id": "arbitrary_a", "cases": [
                    {"canonical_alias": "R053", "score": 18.5,
                     "paired_input_sha256": "a" * 64}]},
                {"id": "arbitrary_b", "cases": [
                    {"canonical_alias": "R053", "score": 21.0,
                     "paired_input_sha256": "b" * 64}]},
            ],
        }
        self.run = {"samples": [
            {"alias": "R053",
             "score": {"arbitrary_a": 18.5, "arbitrary_b": 21.0},
             "seconds": {"arbitrary_a": None, "arbitrary_b": None},
             "measurement_evidence": {
                 "arbitrary_a": {"paired_input_sha256": "a" * 64},
                 "arbitrary_b": {"paired_input_sha256": "b" * 64},
             }},
        ]}

    def test_two_assemblers_on_same_alias_both_verified(self):
        result = check_joined_measurements(self.run, self.evidence)
        self.assertEqual(result, {"arbitrary_a": {"R053"},
                                  "arbitrary_b": {"R053"}})

    def test_first_assembler_tamper_is_detected_despite_second_case(self):
        corrupted = copy.deepcopy(self.run)
        corrupted["samples"][0]["score"]["arbitrary_a"] = 1800000
        with self.assertRaisesRegex(ValueError, "joined score differs"):
            check_joined_measurements(corrupted, self.evidence)

    def test_each_assembler_input_sha_is_checked(self):
        corrupted = copy.deepcopy(self.run)
        corrupted["samples"][0]["measurement_evidence"]["arbitrary_a"][
            "paired_input_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "joined case input hash"):
            check_joined_measurements(corrupted, self.evidence)

    def test_combined_aliases_keep_all_source_receipts(self):
        combined = copy.deepcopy(self.run)
        combined["cohort"] = "combined"
        combined["samples"][0]["alias"] = "R-R053"
        evidence = check_joined_measurements(combined, self.evidence)
        self.assertEqual(evidence, {
            "arbitrary_a": {"R-R053"}, "arbitrary_b": {"R-R053"},
        })
        combined["samples"][0]["score"]["arbitrary_a"] = 999
        with self.assertRaisesRegex(ValueError, "joined score differs"):
            check_joined_measurements(combined, self.evidence)

    def test_no_runtime_synthesized_from_pilot_launcher(self):
        corrupted = copy.deepcopy(self.run)
        corrupted["samples"][0]["seconds"]["arbitrary_a"] = 121.5
        with self.assertRaisesRegex(ValueError, "launcher wall time"):
            check_joined_measurements(corrupted, self.evidence)


if __name__ == "__main__":
    unittest.main()
