"""Focused checks for exact-flank read support; no biological inference from short anchors."""
import gzip
from pathlib import Path
import tempfile
import unittest

from consensus_mask_stage_audit import reverse_complement
from mask_read_allele_support import (
    audit_mask_read_support, fastq_pairs, spanning_alleles,
)

LEFT = "ACGT" * 7 + "GTA"
RIGHT = "TGCA" * 7 + "CTG"
SEED_ALLELE = "AACCGGTT"
ALT_ALLELE = "AATCGGTT"
SEED = LEFT + SEED_ALLELE + RIGHT
REGION = LEFT + "X" * len(SEED_ALLELE) + RIGHT


def run(pairs, region=REGION, seed=SEED):
    return audit_mask_read_support(
        {("S", "R"): region}, {("S", "R"): seed}, pairs)["mask_runs"][0]


class ReadSupportTests(unittest.TestCase):
    def test_exact_seed_and_alternative_pair_counts(self):
        seed_read = LEFT + SEED_ALLELE + RIGHT
        alt_read = LEFT + ALT_ALLELE + RIGHT
        report = run([(seed_read, seed_read), (reverse_complement(seed_read), "NNNN"),
                      (alt_read, "NNNN"), ("NNNN", "NNNN")])
        self.assertTrue(report["unique_seed_flank_bridge"])
        self.assertEqual(report["seed_support_pairs"], 2)
        self.assertEqual(report["alternative_support_pairs"], 1)
        self.assertEqual(report["exact_bridge_pairs"], 3)
        self.assertEqual(report["alternative_alleles"], {ALT_ALLELE: 1})

    def test_disagreeing_mates_are_not_counted_as_support(self):
        report = run([(LEFT + SEED_ALLELE + RIGHT, LEFT + ALT_ALLELE + RIGHT)])
        self.assertEqual(report["ambiguous_pairs"], 1)
        self.assertEqual(report["exact_bridge_pairs"], 0)

    def test_one_flank_or_short_read_is_not_support(self):
        report = run([(LEFT + SEED_ALLELE, SEED_ALLELE + RIGHT),
                      (LEFT + SEED_ALLELE + "N" + RIGHT, "NNNN")])
        self.assertEqual(report["exact_bridge_pairs"], 0)

    def test_repeated_seed_bridge_is_not_certified(self):
        report = run([(SEED, SEED)], seed=SEED + "AAAA" + SEED)
        self.assertFalse(report["unique_seed_flank_bridge"])
        self.assertNotIn("seed_support_pairs", report)

    def test_raw_allele_evidence_without_seed_correspondence(self):
        report = run([(SEED, SEED), (LEFT + ALT_ALLELE + RIGHT, "NNNN")],
                     seed="NNNN")
        self.assertTrue(report["region_unique_flanks"])
        self.assertFalse(report["unique_seed_flank_bridge"])
        self.assertEqual(report["observed_alleles"],
                         {SEED_ALLELE: 1, ALT_ALLELE: 1})
        self.assertNotIn("seed_support_pairs", report)

    def test_repeated_final_flanks_not_counted(self):
        region = REGION + "ACACAC" + REGION
        report = run([(SEED, SEED)], region=region)
        self.assertFalse(report["region_unique_flanks"])
        self.assertEqual(report["exact_bridge_pairs"], 0)

    def test_reverse_complement_allele_detection(self):
        read = reverse_complement(LEFT + ALT_ALLELE + RIGHT)
        self.assertEqual(spanning_alleles(read, LEFT, RIGHT, 8), {ALT_ALLELE})

    def test_invalid_anchor(self):
        with self.assertRaises(ValueError):
            audit_mask_read_support({}, {}, [], anchor=0)

    def test_no_matching_seed_does_not_claim_support(self):
        result = audit_mask_read_support({("S", "R"): REGION}, {}, [(SEED, SEED)])
        self.assertFalse(result["mask_runs"][0]["unique_seed_flank_bridge"])

    def test_fastq_gzip_and_pair_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "r1.fastq.gz", Path(tmp) / "r2.fastq.gz"
            with gzip.open(p1, "wt") as h:
                h.write("@read/1\nACGT\n+\n!!!!\n")
            with gzip.open(p2, "wt") as h:
                h.write("@read/2\nTGCA\n+\n!!!!\n")
            self.assertEqual(list(fastq_pairs(p1, p2, 5)), [("ACGT", "TGCA")])
            with gzip.open(p2, "wt") as h:
                h.write("@wrong/2\nTGCA\n+\n!!!!\n")
            with self.assertRaisesRegex(ValueError, "identifiers"):
                list(fastq_pairs(p1, p2, 5))

    def test_fastq_truncation_and_bad_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "r1.fastq", Path(tmp) / "r2.fastq"
            p1.write_text("@r\nACGT\n+\n!!!\n")
            p2.write_text("@r\nTGCA\n+\n!!!!\n")
            with self.assertRaisesRegex(ValueError, "length mismatch"):
                list(fastq_pairs(p1, p2))
            p1.write_text("@r\nACGT\n+\n")
            with self.assertRaisesRegex(ValueError, "truncated"):
                list(fastq_pairs(p1, p2))

    def test_pair_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "r1.fastq", Path(tmp) / "r2.fastq"
            record = "".join(f"@r{i}\nACGT\n+\n!!!!\n" for i in range(3))
            p1.write_text(record)
            p2.write_text(record)
            self.assertEqual(len(list(fastq_pairs(p1, p2, 2))), 2)


if __name__ == "__main__":
    unittest.main()
