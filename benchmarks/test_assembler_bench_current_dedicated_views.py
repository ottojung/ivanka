"""Current cohort reports preserve independent source and case evidence.

The canonical seven are validated privately by the publisher before the
neutral transform; these tests exercise the public surface after that
transform: attested fork links, exact case preservation and roster union.
"""
import copy
import json
import unittest

from assembler_bench.public_fork_provenance import check as check_fork
from assembler_bench.public_validation import check_joined_measurements
from assembler_bench.site_build import SITE


class DedicatedViewsTests(unittest.TestCase):
    def report(self):
        return copy.deepcopy(json.loads((SITE / "data/runs.json").read_text()))

    def evidence(self):
        return json.loads((SITE / "data/assembler-evidence.json").read_text())

    def test_separate_source_commits_and_fork_links_are_attested(self):
        report = self.report()
        for run in report["runs"]:
            check_fork(SITE, run)
            images = run["micall_fork_provenance"]["images"]
            commits = [item["source_commit"] for item in images.values()]
            branches = [item["source_branch"] for item in images.values()]
            self.assertEqual(len(commits), len(set(commits)))
            self.assertEqual(len(branches), len(set(branches)))
        wrong = self.report()
        wrong["runs"][0]["micall_fork_provenance"]["images"][
            "spades"]["source_branch"] = "bench/assembler-iva"
        with self.assertRaisesRegex(ValueError, "source-attestation"):
            check_fork(SITE, wrong["runs"][0])
        wrong = self.report()
        evidence = wrong["runs"][0]["micall_fork_provenance"]["images"]
        evidence["spades"]["source_commit"] = evidence["iva"]["source_commit"]
        with self.assertRaisesRegex(ValueError, "source-attestation"):
            check_fork(SITE, wrong["runs"][0])

    def test_combined_scores_exactly_preserve_each_measured_case(self):
        report = self.report()
        syn, real, both = report["runs"]
        combined = {row["alias"]: row for row in both["samples"]}
        for prefix, run in (("S", syn), ("R", real)):
            for case in run["samples"]:
                row = combined[prefix + "-" + case["alias"]]
                self.assertEqual(case["score"], row["score"])
                self.assertEqual(case["seconds"], row["seconds"])
                self.assertEqual(case["diagnostics"], row["diagnostics"])
        for alias in ("R-R053", "S-H192", "S-H452"):
            row = combined[alias]
            self.assertTrue(any(value is not None for tool, value in
                                row["score"].items()
                                if tool not in {
                                    "iva", "ivanka", "haploflow", "megahit",
                                    "abyss", "spades", "velvet"}))

    def test_attested_case_joins_are_individually_verified(self):
        report = self.report()
        evidence = self.evidence()
        proofs = {run["cohort"]: check_joined_measurements(run, evidence)
                  for run in report["runs"]}
        # The published case population grows as benchmarks finish.
        for run in report["runs"]:
            cohort = run["cohort"]
            aliases = {row["alias"] for row in run["samples"]}
            for item in evidence["assemblers"]:
                expected = set()
                for case in item.get("cases", []):
                    source = case["cohort"]
                    alias = case["canonical_alias"]
                    if cohort == "combined":
                        alias = ("R-" if source == "real" else "S-") + alias
                    elif source != cohort:
                        continue
                    if alias in aliases:
                        expected.add(alias)
                self.assertEqual(proofs[cohort].get(item["id"], set()), expected)
        self.assertTrue(proofs["real"].get("skesa"))
        self.assertIn("R-R053", proofs["combined"].get("minia", set()))
        corrupted = self.report()
        for sample in corrupted["runs"][2]["samples"]:
            if sample["alias"] == "R-R053":
                sample["score"]["minia"] = 99999
        with self.assertRaisesRegex(ValueError, "joined score differs"):
            check_joined_measurements(corrupted["runs"][2], evidence)

    def test_combined_view_rejects_changed_alignment(self):
        report = self.report()
        wrong = copy.deepcopy(report)
        tool = next((t for t, v in wrong["runs"][2]["samples"][0][
            "score"].items() if v is not None), None)
        if tool is None:
            self.fail("no measured assembler in combined case")
        wrong["runs"][2]["samples"][0]["score"][tool] += 0.42
        with self.assertRaisesRegex(ValueError, "pairwise|joined score"):
            check_public_site_from_report(SITE, wrong)


def check_public_site_from_report(site, report):
    """Recheck a modified report through the real public validation path."""
    import shutil
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp:
        staged = Path(temp) / "bench"
        shutil.copytree(site, staged)
        (staged / "data/runs.json").write_text(json.dumps(report))
        from assembler_bench.site_build import validate_public_site
        return validate_public_site(staged)


if __name__ == "__main__":
    unittest.main()
