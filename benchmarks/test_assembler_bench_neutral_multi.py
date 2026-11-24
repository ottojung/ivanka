"""Regression tests: every assembler's evidence is checked independently."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from assembler_bench.exploratory_publication import publish_neutral
from assembler_bench.public_validation import check_joined_measurements
from assembler_bench.site_build import SITE


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


class RosterStatusTests(unittest.TestCase):
    def test_observation_status_never_uses_placeholder_cases(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        for run in report["runs"]:
            for item in run["roster"]:
                self.assertNotIn({"cohort": run["cohort"]}, item["cases"])
                measured = any(isinstance(sample.get("score", {}).get(
                    item["id"]), (int, float)) for sample in run["samples"])
                if measured:
                    self.assertEqual(item["status"], "measured")
                elif item["status"] == "measured":
                    self.assertTrue(any(isinstance(case.get("score"), (int, float))
                                        for case in item["cases"]))

    def test_new_receipts_can_be_published_without_losing_measurements(self):
        """The live receipt publisher updates neutral evidence and rosters."""
        with tempfile.TemporaryDirectory() as temp:
            staged = Path(temp) / "bench"
            shutil.copytree(SITE, staged)
            evidence, merged, joined = publish_neutral(staged)
            self.assertEqual(len(evidence["assemblers"]), 10)
            self.assertTrue(all(run["tools"] == run["dominance_matrix"]["tools"]
                                for run in merged["runs"]))
            prior = json.loads((SITE / "data/runs.json").read_text())
            for before, after in zip(prior["runs"], merged["runs"]):
                for old, new in zip(before["samples"], after["samples"]):
                    self.assertEqual(old["score"], new["score"])
                    self.assertEqual(old["seconds"], new["seconds"])


if __name__ == "__main__":
    unittest.main()
