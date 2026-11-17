"""Synthetic multi-virus truths, 15% threshold and final MiCall scoring."""
import json
from pathlib import Path
import tempfile
import unittest

from expanded.hxb2_truth import validate
from expanded.hxb2_cohort import attestation, verify_cohort
from expanded.mixed_truth import FAMILIES, haplotypes
from expanded.score import reference_truths, score_sequences
from expanded.synthetic import ACTIVE_FAMILIES, generate_case, generate_cohort


class MultitruthScientificV6(unittest.TestCase):
    def test_replay_and_sibling_abundances_share_exact_biology(self):
        for suffix, short_length in (("hiv", False), ("v3", True)):
            for seed in (0, 7, 15):
                a = haplotypes(f"hcv_{suffix}_15pct", seed)
                b = haplotypes(f"hcv_{suffix}_30pct", seed)
                self.assertEqual(a[0], b[0])
                self.assertEqual(a[1], [0.85, 0.15])
                self.assertEqual(b[1], [0.70, 0.30])
                self.assertEqual(len(a[0][1]) == 550, short_length)
                self.assertGreater(len(a[0][0]), 9000)
                self.assertEqual(a[3]["source_catalog_sha256"],
                                 b[3]["source_catalog_sha256"])

    def test_real_genomic_sources_and_mutations_are_bounded(self):
        for family in FAMILIES:
            genome, _, _, provenance = haplotypes(family, 2)
            self.assertEqual(len(genome), 2)
            for recipe in ("hcv_recipe", "second_recipe"):
                item = provenance[recipe]
                self.assertLessEqual(len(item["mutations"]),
                                     item["unmutated_length"] * 0.05)
            self.assertEqual(provenance["schema"],
                             "ivanka.synthetic.mixed_ancestry.v1")

    def test_signed_threshold_includes_exactly_fifteen_percent(self):
        with tempfile.TemporaryDirectory() as td:
            truth = Path(td) / "truth.fasta"
            a, b = "ACGT" * 50, "TTGG" * 12 + "AC"
            truth.write_text(">a\n" + a + "\n>b\n" + b + "\n")
            for minority, expected in ((0.1499, 1), (0.15, 2), (0.30, 2),
                                       (0.05, 1)):
                spec = {"nominal_fractions": [1-minority, minority],
                        "score_model_revision": 2}
                self.assertEqual(len(reference_truths(spec, truth)), expected)

    def test_balanced_scores_do_not_hide_short_abundant_truth(self):
        with tempfile.TemporaryDirectory() as td:
            truth = Path(td) / "truth.fasta"
            a, b = "ACGT" * 2500, "TTGG" * 137 + "TT"
            truth.write_text(">HCV\n" + a + "\n>V3\n" + b + "\n")
            spec = {"nominal_fractions": [0.85, 0.15],
                    "score_model_revision": 2}
            perfect = score_sequences(spec, truth, [a, b])
            missing = score_sequences(spec, truth, [a])
            self.assertAlmostEqual(perfect["score"], 10000)
            self.assertLess(missing["score"], 6000)
            self.assertEqual(perfect["per_truth"]["truth_1"]["fraction"], 1.)
            self.assertEqual(perfect["combined_alignment_raw"], len(a)+len(b))

    def test_four_mixed_families_generate_valid_fastqs(self):
        with tempfile.TemporaryDirectory() as td:
            for name in FAMILIES:
                meta = generate_case(td, name, 0, pairs=40)
                root = Path(td) / f"{name}-s000"
                self.assertTrue(validate(root))
                self.assertEqual(meta["score_model_revision"], 2)
                self.assertEqual(meta["haplotype_count"], 2)
                self.assertTrue(meta["truth_is_evaluation_only"])
                self.assertEqual(len(meta["sampled_haplotype_pairs"]), 2)

    def test_rejects_falsified_mixed_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            generate_case(td, "hcv_v3_15pct", 1, pairs=40)
            root = Path(td) / "hcv_v3_15pct-s001"
            file = root / "manifest.json"
            data = json.loads(file.read_text())
            data["mixed_ancestry"]["hcv_recipe"]["mutations"] = []
            file.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "ancestry"):
                validate(root)

    def test_committed_full_464_cohort_certificate_is_source_bound(self):
        from expanded.synthetic import fingerprint
        refs = Path(__file__).parent / "expanded/references"
        manifest = refs / "mixed-464-v6-cohort.json"
        proof = json.loads((refs / "mixed-464-v6-validation.json").read_text())
        cohort = json.loads(manifest.read_text())
        self.assertEqual(proof["cohort_sha256"], fingerprint(manifest))
        self.assertEqual(proof["schema"],
                         "ivanka.mixed_viral_truth_validation.v4")
        self.assertEqual(cohort["samples"], 464)
        self.assertEqual(len(cohort["cases"]), 464)
        self.assertEqual(len(set(c["id"] for c in cohort["cases"])), 464)
        self.assertEqual({name: sum(c["id"].startswith(name+"-s")
                                    for c in cohort["cases"])
                          for name in FAMILIES},
                         dict.fromkeys(FAMILIES, 16))
        self.assertEqual(cohort["normal_pairs"], 10000)

    def test_canonical_family_count_and_versioned_truth_proof(self):
        self.assertEqual(len(ACTIVE_FAMILIES), 29)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "cases"
            manifest = generate_cohort(root, seeds=1, pairs=30)
            self.assertEqual(manifest["samples"], 29)
            self.assertEqual(manifest["schema"],
                             "ivanka.expanded.cohort.hxb2.v4")
            self.assertEqual(len(verify_cohort(root, expected=29)), 64)
            proof = attestation(root, expected=29)
            self.assertEqual(proof["schema"],
                             "ivanka.mixed_viral_truth_validation.v4")
            self.assertEqual(proof["min_abundance"], 0.15)


if __name__ == "__main__":
    unittest.main()
