"""Conservative sequence-only tests for masked-locus agreement."""
import random
from pathlib import Path
import tempfile
import unittest

from shared_mask_locus_audit import audit, exact_hits, read_fasta
from consensus_mask_stage_audit import reverse_complement


class SharedMaskTests(unittest.TestCase):
    @staticmethod
    def context():
        rng = random.Random(20261102)
        def seq(n):
            return "".join(rng.choices("ACGT", k=n))
        left, allele, right = seq(31), seq(36), seq(31)
        region = left + "x" * len(allele) + right
        return left, allele, right, region, seq

    def test_shared_allele_even_when_haplotype_flanks_differ(self):
        left, allele, right, region, seq = self.context()
        contigs = [
            ("first", seq(170) + left + allele + right + seq(125)),
            ("second", seq(150) + left + allele + right + seq(140)),
        ]
        r = audit({("S", "R"): region}, contigs)["mask_runs"][0]
        self.assertTrue(r["exact_shared_allele_across_scope"])
        self.assertEqual(r["unique_matching_contigs"], 2)
        self.assertEqual(r["distinct_observed_alleles"], 1)
        self.assertIsNotNone(r["shared_allele_sha256"])

    def test_reverse_orientation_is_counted_once(self):
        left, allele, right, region, seq = self.context()
        contig = seq(80) + left + allele + right + seq(90)
        self.assertEqual(len(exact_hits(reverse_complement(contig), left, right, 36)), 1)
        r = audit({("S", "R"): region},
                  [("forward", contig), ("reverse", reverse_complement(contig))])
        self.assertTrue(r["mask_runs"][0]["exact_shared_allele_across_scope"])

    def test_local_allele_disagreement_prevents_shared_claim(self):
        left, allele, right, region, seq = self.context()
        alternate = ("C" if allele[0] != "C" else "A") + allele[1:]
        contigs = [("a", seq(65) + left + allele + right),
                   ("b", seq(65) + left + alternate + right)]
        result = audit({("S", "R"): region}, contigs)["mask_runs"][0]
        self.assertFalse(result["exact_shared_allele_across_scope"])
        self.assertEqual(result["distinct_observed_alleles"], 2)

    def test_repeated_exact_locus_is_ambiguous(self):
        left, allele, right, region, seq = self.context()
        repeat = left + allele + right
        r = audit({("S", "R"): region},
                  [("repeat", seq(50) + repeat + seq(50) + repeat)])["mask_runs"][0]
        self.assertFalse(r["exact_shared_allele_across_scope"])
        self.assertEqual(r["ambiguous_contigs"], ["repeat"])

    def test_missing_or_empty_scope_fails_closed(self):
        left, allele, right, region, seq = self.context()
        matching = left + allele + right
        missing = seq(150)
        reports = audit({("S", "R"): region}, [("yes", matching), ("no", missing)])
        self.assertFalse(reports["mask_runs"][0]["exact_shared_allele_across_scope"])
        self.assertEqual(reports["mask_runs"][0]["missing_contigs"], ["no"])
        empty = audit({("S", "R"): region}, [("short", matching)], min_length=500)
        self.assertFalse(empty["mask_runs"][0]["exact_shared_allele_across_scope"])

    def test_edge_masks_and_invalid_parameters(self):
        left, allele, right, region, seq = self.context()
        edge = "X" * 36 + right
        r = audit({("S", "R"): edge}, [("a", left + allele + right)])
        self.assertFalse(r["mask_runs"][0]["exact_shared_allele_across_scope"])
        with self.assertRaises(ValueError):
            audit({}, [], anchor=0)
        with self.assertRaises(ValueError):
            audit({}, [], min_length=-1)

    def test_sample_region_filter_and_fasta_parser(self):
        left, allele, right, region, seq = self.context()
        rows = {("S1", "R1"): region, ("S2", "R2"): region}
        result = audit(rows, [("c", left + allele + right)],
                       sample="S2", region="R2")
        self.assertEqual(len(result["mask_runs"]), 1)
        self.assertEqual(result["mask_runs"][0]["sample"], "S2")
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "reads.fasta"
            p.write_text(">a description\nacgt\nTGCA\n>b\nTTTT\n")
            self.assertEqual(read_fasta(p), [("a", "ACGTTGCA"), ("b", "TTTT")])
            p.write_text(">empty\n")
            with self.assertRaises(ValueError):
                read_fasta(p)


if __name__ == "__main__":
    unittest.main()
