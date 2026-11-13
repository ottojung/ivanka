"""Only coherent dedicated seven-way views can replace shared-source runs."""
import copy
import json
import unittest

from assembler_bench.combined_public import preview as combine
from assembler_bench.current_validation import (
    DEDICATED_COMBINED, DEDICATED_REAL, DEDICATED_SYNTH, check_current)
from assembler_bench.site_build import SITE


class DedicatedViewsTests(unittest.TestCase):
    def report(self):
        report = copy.deepcopy(json.loads((SITE/"data/runs.json").read_text()))
        synthetic, real, _ = report["runs"]
        synthetic["id"] = DEDICATED_SYNTH
        real["id"] = DEDICATED_REAL
        for run in (synthetic, real):
            proof = run["micall_fork_provenance"]
            proof["attestation_schema"] = (
                "ivanka.assembler-bench.dedicated-fork-images.v1")
            for index, (name, data) in enumerate(
                    sorted(proof["images"].items()), 1):
                commit = format(index, "x") * 40
                data["source_branch"] = "bench/assembler-" + name
                data["source_commit"] = commit
                data["source_url"] = (
                    "https://github.com/ottojung/MiCall/tree/" + commit)
        from expanded.gate import SCORE_ORIGIN
        synthetic["score_origin"] = SCORE_ORIGIN
        real["score_origin"] = SCORE_ORIGIN
        report["runs"] = [synthetic, real, combine(synthetic, real)]
        assert report["runs"][2]["id"] == DEDICATED_COMBINED
        return report

    def test_dedicated_cohorts_need_unique_branch_commits(self):
        report=self.report()
        check_current(report)
        wrong=copy.deepcopy(report)
        wrong["runs"][0]["micall_fork_provenance"]["images"][
            "spades"]["source_branch"]="bench/assembler-iva"
        with self.assertRaisesRegex(ValueError, "seven dedicated"):
            check_current(wrong)
        wrong=self.report()
        proof=wrong["runs"][0]["micall_fork_provenance"]["images"]
        proof["spades"]["source_commit"]=proof["iva"]["source_commit"]
        with self.assertRaisesRegex(ValueError, "seven dedicated"):
            check_current(wrong)

    def test_combined_scores_are_exact_copies_of_each_measured_case(self):
        report=self.report()
        synthetic, real, both=report["runs"]
        for original, published in zip(
                synthetic["samples"]+real["samples"], both["samples"]):
            self.assertEqual(original["score"], published["score"])
            self.assertEqual(original["seconds"], published["seconds"])

    def test_mismatched_score_origins_are_rejected(self):
        report=self.report()
        report["runs"][1]["score_origin"]="different-method"
        with self.assertRaisesRegex(ValueError,"identical local scores"):
            check_current(report)

    def test_combined_view_is_derived_from_both_source_cohorts(self):
        report=self.report()
        wrong=copy.deepcopy(report)
        if wrong["runs"][2]["samples"]:
            wrong["runs"][2]["samples"][0]["score"]["ivanka"]=0.42
        else:
            wrong["runs"][2]["source_runs"]=["unrelated-run"]
        with self.assertRaisesRegex(ValueError, "does not preserve original alignment points"):
            check_current(wrong)


if __name__ == "__main__":
    unittest.main()
