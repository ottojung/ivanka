"""Do not confuse long contigs with source-supported haplotype phase."""
import tempfile
import unittest
from pathlib import Path

from synthetic_phase_pairs import generate, reverse_complement
from synthetic_phase_fidelity import analyze, anchored_allele, fasta_records


class SyntheticPhaseFidelityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def linked(self):
        return generate(self.root / "linked", length=1200,
                        variants=(400, 600), pairs_per_haplotype=1000, seed=4)

    def test_true_coupled_haplotype_is_consistent_with_bridging_pairs(self):
        truth = self.linked()
        self.assertGreater(truth["read_pairs_directly_observing_both_variants"], 0)
        result = analyze(truth, [("true", truth["phase_coupled_haplotypes"][0])])
        self.assertEqual(result["contigs"][0]["classification"],
                         "consistent_with_source_phase")
        self.assertEqual(result["unsupported_recombinant_count"], 0)

    def test_cross_haplotype_recombinant_is_rejected(self):
        truth = self.linked()
        bad = truth["phase_decoupled_haplotypes"][0]
        result = analyze(truth, [("recombined", bad)])
        self.assertEqual(result["contigs"][0]["classification"],
                         "unsupported_recombinant")
        self.assertEqual(result["unsupported_recombinant_count"], 1)

    def test_correct_phase_is_not_claimable_without_bridging_pairs(self):
        truth = generate(self.root / "unlinked", pairs_per_haplotype=300)
        records = [(f"hap{i}", s) for i, s in
                   enumerate(truth["phase_coupled_haplotypes"])]
        result = analyze(truth, records)
        self.assertEqual(result["unidentifiable_phase_count"], 2)
        self.assertEqual(result["unsupported_recombinant_count"], 0)

    def test_reverse_complement_only_changes_orientation(self):
        truth = self.linked()
        seq = reverse_complement(truth["phase_coupled_haplotypes"][1])
        result = analyze(truth, [("reverse", seq)])
        self.assertEqual(result["contigs"][0]["orientation"], "-")
        self.assertEqual(result["contigs"][0]["classification"],
                         "consistent_with_source_phase")

    def test_unobserved_variant_is_not_imputed(self):
        truth = self.linked()
        partial = truth["phase_coupled_haplotypes"][0][0:450]
        result = analyze(truth, [("partial", partial)])
        self.assertEqual(result["contigs"][0]["classification"],
                         "unresolved_or_ambiguous")
        self.assertIsNone(result["contigs"][0]["orientation"])

    def test_unique_local_flank_is_required(self):
        self.assertIsNone(anchored_allele("AAAAAAA", "ACGT"*100, 5, 25))
        with self.assertRaises(ValueError):
            analyze({"variant_positions_zero_based": [10],
                     "phase_coupled_haplotypes": ["A", "B"]}, [])

    def test_fasta_reader_preserves_exact_paths(self):
        file = self.root / "contigs.fa"
        file.write_text(">path1\nACG\nT\n>path2 description\nGCTA\n")
        self.assertEqual(fasta_records(file),
                         [("path1", "ACGT"), ("path2 description", "GCTA")])
        with self.assertRaises(FileNotFoundError):
            fasta_records(self.root / "missing.fa")


if __name__ == "__main__":
    unittest.main()
