"""Branch names must identify the actual pinned MiCall adapter commit."""
import copy
import json
import unittest

from assembler_bench.adapter_branch_refs import adapter_provenance, branch_for
from assembler_bench.public_validation import check_evidence
from assembler_bench.site_build import SITE


class BranchProvenanceTests(unittest.TestCase):
    def test_every_public_adapter_has_exact_branch_and_commit_url(self):
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        self.assertEqual(check_evidence(evidence), len(evidence["assemblers"]))
        for item in evidence["assemblers"]:
            expected = adapter_provenance(item["id"], item["adapter_commit"])
            self.assertEqual(item["source_branch"], expected["source_branch"])
            self.assertEqual(item["source_url"], expected["source_url"])

    def test_missing_or_wrong_branch_is_rejected(self):
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        for branch in (None, "bench/unrelated"):
            changed = copy.deepcopy(evidence)
            changed["assemblers"][0]["source_branch"] = branch
            with self.assertRaisesRegex(ValueError, "branch or commit URL"):
                check_evidence(changed)

    def test_unknown_commit_and_wrong_assembler_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing verified"):
            branch_for("skesa", "0" * 40)
        with self.assertRaisesRegex(ValueError, "missing verified"):
            branch_for("other", "2fb3cd5af8769f834635b21187738cf90565c349")
