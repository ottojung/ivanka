"""Only low-depth read files change in the prospective v2 HXB2 cohort."""
import json
from pathlib import Path
import tempfile
import unittest

from expanded.hxb2_cohort import attestation, verify_cohort
from expanded.hxb2_lowdepth_v2 import derive
from expanded.synthetic import generate_cohort


class LowDepthLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / "hxb2-v1"
        self.revised = self.root / "hxb2-v2"
        generate_cohort(self.original, seeds=1, pairs=80)
        self.v1_digest = verify_cohort(self.original, expected=25)

    def test_one_family_changes_only_paired_reads(self):
        revised = derive(self.original, self.revised)
        self.assertEqual(revised["samples"], 25)
        self.assertEqual(revised["changed_read_cases"], ["low_depth-s000"])
        self.assertEqual(revised["source_cohort_sha256"], self.v1_digest)
        self.assertEqual(len(revised["unchanged_case_sha256"]), 24)
        self.assertNotEqual(verify_cohort(self.revised, expected=25),
                            self.v1_digest)
        orig = json.loads((self.original / "low_depth-s000/manifest.json").read_text())
        new = json.loads((self.revised / "low_depth-s000/manifest.json").read_text())
        self.assertEqual((orig["pairs"], new["pairs"]), (20, 40))
        self.assertEqual(orig["sha256"][orig["hidden_truth_file"]],
                         new["sha256"][new["hidden_truth_file"]])
        for name in orig["read_files"]:
            self.assertNotEqual(orig["sha256"][name], new["sha256"][name])
        for name in ("clonal-s000", "iid_errors-s000", "pcr_jackpot-s000"):
            a = self.original / name
            b = self.revised / name
            for file in ("manifest.json", "reads/R1.fastq.gz",
                         "reads/R2.fastq.gz", "hidden-truth/haplotypes.fasta"):
                self.assertEqual((a / file).read_bytes(), (b / file).read_bytes())
        self.assertEqual(verify_cohort(self.original, expected=25),
                         self.v1_digest)

    def test_v2_is_eligible_for_full_micall_gate(self):
        from expanded.gate import eligible_truth, summarize_gate
        from expanded.adapters import ASSEMBLERS
        proof = attestation(self.original, expected=25)
        derive(self.original, self.revised)
        v2 = attestation(self.revised, expected=25)
        self.assertTrue(eligible_truth({"truth_validation": proof}))
        self.assertTrue(eligible_truth({"truth_validation": v2}))
        def row(sample, cohort, family=None, attested=None):
            return {"id": sample, "cohort": cohort, "family": family,
                    "input_sha256": "b" * 64, "truth_validation": attested,
                    "results": {tool: {
                        "status": "success", "sha256": "a" * 64,
                        "seconds": 1 if tool == "ivanka" else 2,
                        "score": 120 if tool == "ivanka" else 100,
                        "score_origin": "micall_final_max_reference_panel_v1",
                        "timing_origin": "micall_in_container_monotonic_v1",
                    } for tool in ASSEMBLERS}}
        real = row("real-1", "real")
        synthetic = row("clonal-s000", "synthetic", "clonal", v2)
        qualified = summarize_gate(
            [real, synthetic], real_count=1,
            synthetic_seeds=1, families=("clonal",))
        self.assertTrue(qualified["pass"], qualified["errors"])
        self.assertEqual(qualified["synthetic_truth_schema"], v2["schema"])
        mixed = row("low_depth-s000", "synthetic", "low_depth", proof)
        wrong = summarize_gate(
            [real, synthetic, mixed], real_count=1,
            synthetic_seeds=1, families=("clonal", "low_depth"))
        self.assertFalse(wrong["pass"])
        self.assertIn("synthetic:mixed_truth_cohorts", wrong["errors"])

    def test_separate_truth_proofs_cannot_cross_cohorts(self):
        original = attestation(self.original, expected=25)
        derive(self.original, self.revised)
        revised = attestation(self.revised, expected=25)
        self.assertEqual(original["schema"], "ivanka.hxb2_truth_validation.v1")
        self.assertEqual(revised["schema"], "ivanka.hxb2_truth_validation.v2")
        self.assertNotEqual(original["verification_sha256"],
                            revised["verification_sha256"])

    def test_refuses_replacement_or_unverified_non_low_depth(self):
        derive(self.original, self.revised)
        with self.assertRaises(FileExistsError):
            derive(self.original, self.revised)
        wrong = self.revised / "clonal-s000/manifest.json"
        data = json.loads(wrong.read_text())
        data["pairs"] += 1
        wrong.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify_cohort(self.revised, expected=25)


if __name__ == "__main__":
    unittest.main()
