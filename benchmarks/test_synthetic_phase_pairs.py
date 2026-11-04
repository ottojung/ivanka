"""Synthetic two-haplotype phase identifiability negative controls."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from synthetic_phase_pairs import generate, paired_reads, reverse_complement


class PhaseIdentifiabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_unlinked_variants_have_two_identical_read_explanations(self):
        truth = generate(self.root / "unlinked", variants=(280, 900),
                         pairs_per_haplotype=600, seed=4)
        self.assertEqual(truth["read_pairs_directly_observing_both_variants"], 0)
        self.assertTrue(truth["alternative_phase_explains_identical_original_reads"])
        self.assertNotEqual(truth["phase_coupled_haplotypes"],
                            truth["phase_decoupled_haplotypes"])
        for locus in truth["variant_positions_zero_based"]:
            self.assertEqual(sorted(h[locus] for h in
                                    truth["phase_coupled_haplotypes"]),
                             sorted(h[locus] for h in
                                    truth["phase_decoupled_haplotypes"]))
        self.assertEqual(truth["original_qname_pairs"], 1200)
        self.assertEqual(json.loads(
            (self.root / "unlinked/truth.json").read_text()), truth)

    def test_bridging_original_pairs_distinguish_opposite_phase(self):
        truth = generate(self.root / "linked", length=1200,
                         variants=(400, 600), pairs_per_haplotype=1000, seed=4)
        self.assertGreater(truth["read_pairs_directly_observing_both_variants"], 0)
        self.assertFalse(truth["alternative_phase_explains_identical_original_reads"])

    def test_fastq_names_mate_orientations_and_quality(self):
        generate(self.root / "reads", pairs_per_haplotype=20, seed=3)
        files = [self.root / f"reads/synthetic_R{mate}.fastq.gz"
                 for mate in (1, 2)]
        records = []
        for file in files:
            with gzip.open(file, "rt") as stream:
                lines = stream.read().splitlines()
            self.assertEqual(len(lines), 40 * 4)
            records.append([lines[i:i+4] for i in range(0, len(lines), 4)])
        names = []
        for r1, r2 in zip(*records):
            self.assertEqual(r1[0].split()[0], r2[0].split()[0])
            self.assertTrue(r1[0].endswith(" 1:N:0:0"))
            self.assertTrue(r2[0].endswith(" 2:N:0:0"))
            self.assertEqual(len(r1[1]), 100)
            self.assertEqual(len(r2[1]), 100)
            self.assertEqual(r1[3], "I"*100)
            self.assertEqual(r2[3], "I"*100)
            names.append(r1[0].split()[0])
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(reverse_complement("ACGT"), "ACGT")

    def test_determinism_even_with_errors(self):
        args = dict(pairs_per_haplotype=30, seed=2026, error_rate=0.03)
        a = generate(self.root / "a", **args)
        b = generate(self.root / "b", **args)
        self.assertEqual(a, b)
        self.assertTrue(a["alternative_phase_explains_identical_original_reads"])
        for name in ("synthetic_R1.fastq.gz", "synthetic_R2.fastq.gz",
                     "truth.json"):
            self.assertEqual((self.root/"a"/name).read_bytes(),
                             (self.root/"b"/name).read_bytes())

    def test_original_synthetic_data_is_never_overwritten(self):
        path = self.root / "protected"
        generate(path, pairs_per_haplotype=2, seed=9)
        original = (path / "synthetic_R1.fastq.gz").read_bytes()
        with self.assertRaises(FileExistsError):
            generate(path, pairs_per_haplotype=2, seed=10)
        self.assertEqual((path / "synthetic_R1.fastq.gz").read_bytes(),
                         original)

    def test_invalid_geometry_is_rejected(self):
        for kwargs in (dict(length=200, fragment_length=300),
                       dict(read_length=310, fragment_length=300),
                       dict(variants=(20, 20)),
                       dict(variants=(900, 20)),
                       dict(variants=(20, 1400)),
                       dict(pairs_per_haplotype=0),
                       dict(error_rate=1.0)):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    generate(self.root / "bad", **kwargs)

    def test_explicit_mate_geometry_no_imputed_insert(self):
        seq="ACGT"*300
        a,b=paired_reads(seq, 100, 50, 250)
        self.assertEqual(a,seq[100:150])
        self.assertEqual(reverse_complement(b),seq[300:350])


if __name__ == "__main__":
    unittest.main()
