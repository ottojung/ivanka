"""Current seven-assembler reports preserve independent source and case evidence."""
import copy
import json
import unittest

from assembler_bench.current_validation import check_current
from assembler_bench.public_fork_provenance import check as check_fork
from assembler_bench.site_build import SITE


class DedicatedViewsTests(unittest.TestCase):
    def report(self):
        return copy.deepcopy(json.loads((SITE/"data/runs.json").read_text()))

    def test_separate_source_commits_and_fork_links_are_attested(self):
        report=self.report()
        check_current(report)
        for run in report["runs"]:
            check_fork(SITE,run)
            commits=[item["source_commit"] for item in
                     run["micall_fork_provenance"]["images"].values()]
            branches=[item["source_branch"] for item in
                      run["micall_fork_provenance"]["images"].values()]
            self.assertEqual(len(commits),len(set(commits)))
            self.assertEqual(len(branches),len(set(branches)))
        wrong=self.report()
        wrong["runs"][0]["micall_fork_provenance"]["images"][
            "spades"]["source_branch"]="bench/assembler-iva"
        with self.assertRaisesRegex(ValueError,"source-attestation"):
            check_fork(SITE,wrong["runs"][0])
        wrong=self.report()
        evidence=wrong["runs"][0]["micall_fork_provenance"]["images"]
        evidence["spades"]["source_commit"]=evidence["iva"]["source_commit"]
        with self.assertRaisesRegex(ValueError,"source-attestation"):
            check_fork(SITE,wrong["runs"][0])

    def test_combined_scores_exactly_preserve_each_measured_case(self):
        report=self.report()
        check_current(report)
        syn,real,both=report["runs"]
        combined={row["alias"]:row for row in both["samples"]}
        for prefix,run in (("S",syn),("R",real)):
            for case in run["samples"]:
                row=combined[prefix+"-"+case["alias"]]
                self.assertEqual(case["score"],row["score"])
                self.assertEqual(case["seconds"],row["seconds"])
                self.assertEqual(case["diagnostics"],row["diagnostics"])

    def test_mismatched_alignment_method_is_rejected(self):
        report=self.report()
        report["runs"][1]["score_origin"]="different-method"
        with self.assertRaisesRegex(ValueError,"metadata/qualification"):
            check_current(report)

    def test_combined_view_rejects_changed_alignment(self):
        report=self.report()
        wrong=copy.deepcopy(report)
        if wrong["runs"][2]["samples"]:
            sample=wrong["runs"][2]["samples"][0]
            tool=next((t for t,s in sample["score"].items() if s is not None),None)
            if tool is not None:
                sample["score"][tool]+=0.42
            else:
                wrong["runs"][2]["source_runs"]=["unrelated-run"]
        else:
            wrong["runs"][2]["source_runs"]=["unrelated-run"]
        with self.assertRaisesRegex(ValueError,
                                    "combined source scientific values were changed|combined view"):
            check_current(wrong)


if __name__=="__main__":
    unittest.main()
