"""Regression tests for replacement HXB2 synthetic cohort and untouched split."""
import json
import random
import tempfile
import unittest
from pathlib import Path

from expanded.hxb2_cohort import attestation, verify_cohort
from expanded.hxb2_truth import haplotypes
from expanded.read_model import low_depth_pair_count, quality_profile, quality_values
from expanded.score import reference_truths, score_sequences
from expanded.synthetic import generate_case, generate_cohort, read_errors


class ScientificSyntheticV4(unittest.TestCase):
    def test_matched_single_strain_biology_is_orthogonal_to_read_stress(self):
        for seed in (0, 5, 12):
            base = haplotypes("clonal", seed, revision=2)[0]
            for family in ("iid_errors", "gc_dropout", "quality_decay",
                           "pcr_jackpot", "long_inserts", "low_depth"):
                self.assertEqual(base, haplotypes(family, seed, revision=2)[0])

    def test_shared_two_strain_truth_is_orthogonal_to_abundance(self):
        for seed in (0, 1, 10):
            shared = haplotypes("minority_5pct", seed, revision=2)[0]
            for family in ("minority_30pct", "equal_strains"):
                self.assertEqual(shared, haplotypes(family, seed, revision=2)[0])

    def test_equal_abundance_tie_scores_either_true_haplotype(self):
        with tempfile.TemporaryDirectory() as td:
            truth = Path(td) / "truth.fasta"
            a, b = "ACGT" * 50, "TTGG" * 50
            truth.write_text(">a\n" + a + "\n>b\n" + b + "\n")
            meta = {"nominal_fractions": [0.5, 0.5]}
            self.assertEqual(len(reference_truths(meta, truth)), 2)
            for candidate in (a, b):
                result = score_sequences(meta, truth, [candidate])
                self.assertEqual(result["score"], 200)
                self.assertTrue(result["dominant_exact"])
                self.assertEqual(result["reference_count"], 2)

    def test_low_depth_is_truly_sparse_and_seed_stratified(self):
        depth = [low_depth_pair_count(9700, seed, 10000)
                 for seed in range(16)]
        self.assertEqual([d[1] for d in depth], [3, 6, 12, 24] * 4)
        self.assertTrue(all(abs(n * 300 / 9700 - d) < 0.1 for n, d in depth))
        self.assertLess(max(n for n, _ in depth), 1000)

    def test_quality_model_only_contains_aggregate_quantiles(self):
        profile = quality_profile()
        self.assertEqual(profile["sampled_read_counts"], [25334, 25334])
        self.assertEqual(profile["files_per_mate"], [198, 198])
        self.assertNotIn("read_sequences", profile)
        for mate in (1, 2):
            a = quality_values(random.Random(7), mate)
            b = quality_values(random.Random(7), mate)
            self.assertEqual(a, b)
            self.assertEqual(len(a), 150)
            self.assertTrue(all(0 <= q <= 41 for q in a))

    def test_quality_decay_and_bad_second_mate_are_expressed_in_fastq(self):
        seq = "ACGT" * 38
        _, base = read_errors(seq[:150], "iid_errors", random.Random(21),
                              mate=2, start=0)
        _, poor = read_errors(seq[:150], "mate_quality_asymmetry",
                              random.Random(21), mate=2, start=0)
        self.assertLess(sum(ord(x) for x in poor), sum(ord(x) for x in base))
        _, normal = read_errors(seq[:150], "clonal", random.Random(21),
                                mate=1, start=0)
        _, decay = read_errors(seq[:150], "quality_decay", random.Random(21),
                               mate=1, start=0)
        self.assertLess(sum(ord(x) for x in decay[115:]),
                        sum(ord(x) for x in normal[115:]))

    def test_holdout_is_disjoint_versioned_and_not_scored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "validation"
            cohort = generate_cohort(root, seeds=1, pairs=30,
                                     split="validation")
            self.assertEqual(cohort["schema"], "ivanka.expanded.cohort.hxb2.v4")
            self.assertEqual(cohort["split"], "validation")
            self.assertEqual(cohort["seed_start"], 900)
            self.assertTrue(all(row["id"].endswith("-s900")
                                for row in cohort["cases"]))
            self.assertEqual(len(verify_cohort(root, expected=29)), 64)
            self.assertEqual(attestation(root, expected=29)["schema"],
                             "ivanka.mixed_viral_truth_validation.v4")
            altered = json.loads((root / "cohort.json").read_text())
            altered["seed_start"] = 0
            (root / "cohort.json").write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "split"):
                verify_cohort(root, expected=29)

    def test_completed_cohort_resume_is_verified_not_rewritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "development"
            first = generate_cohort(root, seeds=1, pairs=40)
            before = (root / "cohort.json").read_bytes()
            second = generate_cohort(root, seeds=1, pairs=40, resume=True)
            self.assertEqual(first, second)
            self.assertEqual(before, (root / "cohort.json").read_bytes())

    def test_interrupted_cohort_resume_recovers_verified_cases_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "development"
            generate_cohort(root, seeds=1, pairs=40)
            expected = (root / "cohort.json").read_bytes()
            (root / "cohort.json").rename(root / "cohort.json.pending")
            generate_cohort(root, seeds=1, pairs=40, resume=True)
            self.assertEqual((root / "cohort.json").read_bytes(), expected)
            damaged = root / "clonal-s000/manifest.json"
            record = json.loads(damaged.read_text())
            record["requested_normal_pairs"] = 60
            damaged.write_text(json.dumps(record))
            (root / "cohort.json").unlink()
            with self.assertRaisesRegex(ValueError, "not verified"):
                generate_cohort(root, seeds=1, pairs=40, resume=True)

    def test_old_and_new_generation_are_distinct_versions(self):
        with tempfile.TemporaryDirectory() as td:
            new = generate_case(td, "clonal", 0, pairs=30)
            self.assertEqual(new["schema"], "ivanka.expanded.synthetic.hxb2.v2")
            self.assertEqual(new["truth_model_revision"], 2)
            self.assertEqual(new["read_model_revision"], 2)
            self.assertEqual(len(new["quality_profile_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
