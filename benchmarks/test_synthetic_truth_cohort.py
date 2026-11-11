import gzip
import tempfile
import unittest
from pathlib import Path

from known_truth_eval import evaluate
from produce_exact_coverage import longest_max_conseq
from synthetic_truth_cohort import CASES, generate_case


class SyntheticTruthTests(unittest.TestCase):
    def test_all_known_truth_cases_really_prefer_better_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case in CASES:
                with self.subTest(case=case):
                    spec = generate_case(tmp, case, pairs=60)
                    folder = Path(tmp) / case
                    better = evaluate(folder / "truth.fasta",
                                      folder / "better.fasta")
                    worse = evaluate(folder / "truth.fasta",
                                     folder / "worse.fasta")
                    self.assertGreater(
                        better["best_global_truth_score_sum"],
                        worse["best_global_truth_score_sum"])
                    self.assertEqual(
                        better["exact_truth_haplotypes_recovered"],
                        spec["truth_haplotype_count"])
                    self.assertEqual(worse["exact_truth_haplotypes_recovered"], 0)
                    self.assertTrue(spec["truth_is_evaluation_only"])
                    with gzip.open(folder / "synthetic_R1.fastq.gz", "rt") as f:
                        lines = f.readlines()
                    self.assertEqual(len(lines), 4*spec["pairs"])
                    self.assertEqual(len(lines[1].strip()), spec["read_length"])
                    self.assertTrue(lines[0].startswith("@truth:"))
                    with self.assertRaises(FileExistsError):
                        generate_case(tmp, case, pairs=60)

    def test_reproducible_hashes(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first = generate_case(one, "clonal_exact", pairs=40)
            second = generate_case(two, "clonal_exact", pairs=40)
            self.assertEqual(first["files_sha256"], second["files_sha256"])

    def test_longest_max_conseq_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "conseq.csv"
            f.write_text(
                "seed,consensus-percent-cutoff,sequence\n"
                "known,MAX,ACGT\n"
                "short,MAX,AC\n"
                "nope,0.1," + "A"*30 + "\n"
                "unknown-seed,MAX," + "G"*50 + "\n")
            self.assertEqual(longest_max_conseq(f), ("known", "ACGT"))
            f.write_text("seed,consensus-percent-cutoff,sequence\nmissing,0.1,ACGT\n")
            with self.assertRaises(ValueError):
                longest_max_conseq(f)


if __name__ == "__main__":
    unittest.main()
