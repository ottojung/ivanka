"""Focused checks for exact-flank read support; no biological inference from short anchors."""
import gzip
from pathlib import Path
import tempfile
import unittest

from consensus_mask_stage_audit import reverse_complement
from mask_read_allele_support import (
    _count_spaced_flanks, audit_mask_read_support, fastq_pairs, spanning_alleles,
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

    def test_cross_region_bridge_is_not_region_specific(self):
        other = "TTTT" + LEFT + ALT_ALLELE + RIGHT + "GGGG"
        reports = audit_mask_read_support(
            {("S", "R"): REGION, ("S", "R2"): other},
            {("S", "R"): SEED}, [(SEED, SEED)])["mask_runs"]
        report = next(x for x in reports if x["region"] == "R")
        self.assertEqual(report["other_region_bridges"], 1)
        self.assertFalse(report["globally_unique_flank_bridge"])
        self.assertEqual(report["exact_bridge_pairs"], 1)

    def test_region_filter_does_not_hide_cross_region_ambiguity(self):
        other = "TTTT" + LEFT + ALT_ALLELE + RIGHT + "GGGG"
        result = audit_mask_read_support(
            {("S", "R"): REGION, ("S", "R2"): other},
            {("S", "R"): SEED}, [(SEED, "NNNN")], report_region="R")
        self.assertEqual(len(result["mask_runs"]), 1)
        report = result["mask_runs"][0]
        self.assertEqual(report["other_region_bridges"], 1)
        self.assertFalse(report["globally_unique_flank_bridge"])

    def test_reverse_complement_bridge_in_same_region_is_ambiguous(self):
        region = REGION + "AAAA" + reverse_complement(LEFT + ALT_ALLELE + RIGHT)
        report = run([(SEED, "NNNN")], region=region)
        self.assertEqual(region.count(LEFT), 1)
        self.assertEqual(region.count(RIGHT), 1)
        self.assertFalse(report["region_unique_flanks"])
        self.assertEqual(report["exact_bridge_pairs"], 0)

    def test_palindromic_bridge_is_one_locus_not_two_orientations(self):
        # The masked physical interval is self-reverse-complementary.
        region = "ACGXXXXCGT"
        read = "ACGATATCGT"
        self.assertEqual(_count_spaced_flanks(region, "ACG", "CGT", 4), 1)
        report = audit_mask_read_support(
            {("S", "R"): region}, {("S", "R"): read},
            [(read, "NNNN")], anchor=3)["mask_runs"][0]
        self.assertTrue(report["region_unique_flanks"])
        self.assertEqual(report["exact_bridge_pairs"], 1)
        # A symmetric locus still does not certify seed-strand orientation.
        self.assertFalse(report["unique_seed_flank_bridge"])

    def test_palindromic_flanks_do_not_force_an_allele_orientation(self):
        region = "ACGXXXXCGT"
        read = "ACGAAGCCGT"
        report = audit_mask_read_support(
            {("S", "R"): region}, {("S", "R"): read},
            [(read, "NNNN")], anchor=3)["mask_runs"][0]
        self.assertTrue(report["region_unique_flanks"])
        self.assertEqual(report["ambiguous_pairs"], 1)
        self.assertEqual(report["exact_bridge_pairs"], 0)
        self.assertEqual(_count_spaced_flanks(region + "TT" + region, "ACG", "CGT", 4), 2)

    def test_reverse_complement_other_region(self):
        other = reverse_complement(LEFT + ALT_ALLELE + RIGHT)
        reports = audit_mask_read_support(
            {("S", "R"): REGION, ("S", "R2"): other}, {}, [(SEED, "NNNN")])["mask_runs"]
        self.assertEqual(reports[0]["other_region_bridges"], 1)

    def test_unrelated_sample_and_gap_are_not_ambiguous(self):
        reports = audit_mask_read_support(
            {("S", "R"): REGION, ("S", "R2"): LEFT + "C" * 9 + RIGHT,
             ("T", "R3"): SEED}, {}, [(SEED, SEED)])["mask_runs"]
        self.assertTrue(next(x for x in reports if x["sample"] == "S")["globally_unique_flank_bridge"])

    def test_duplicate_seed_region_prevents_region_attribution(self):
        regions = {("S", "R"): REGION}
        seeds = {("S", "R"): SEED, ("S", "R2"): "GG" + SEED + "TT"}
        report = audit_mask_read_support(regions, seeds, [(SEED, "NNNN")])["mask_runs"][0]
        self.assertTrue(report["globally_unique_flank_bridge"])
        self.assertTrue(report["unique_seed_flank_bridge"])
        self.assertEqual(report["other_seed_bridges"], 1)
        self.assertFalse(report["globally_unique_seed_flank_bridge"])
        self.assertFalse(report["region_attributable_bridge"])
        self.assertEqual(report["seed_support_pairs"], 1)
        self.assertEqual(report["region_attributable_seed_support_pairs"], 0)

    def test_reverse_complement_other_seed_prevents_attribution(self):
        seeds = {("S", "R"): SEED, ("S", "R2"): reverse_complement(SEED)}
        report = audit_mask_read_support(
            {("S", "R"): REGION}, seeds, [(SEED, "NNNN")])["mask_runs"][0]
        self.assertEqual(report["other_seed_bridges"], 1)
        self.assertFalse(report["region_attributable_bridge"])

    def test_unrelated_seed_and_final_region_allow_attribution(self):
        seeds = {("S", "R"): SEED, ("T", "R2"): SEED}
        report = audit_mask_read_support(
            {("S", "R"): REGION}, seeds,
            [(SEED, "NNNN"), (LEFT + ALT_ALLELE + RIGHT, "NNNN")])["mask_runs"][0]
        self.assertTrue(report["region_attributable_bridge"])
        self.assertEqual(report["region_attributable_seed_support_pairs"], 1)
        self.assertEqual(report["region_attributable_alternative_support_pairs"], 1)

    def test_other_final_region_blocks_attribution_even_if_seed_unique(self):
        regions = {("S", "R"): REGION, ("S", "R2"): "GG" + SEED + "TT"}
        report = audit_mask_read_support(
            regions, {("S", "R"): SEED}, [(SEED, "NNNN")],
            report_region="R")["mask_runs"][0]
        self.assertTrue(report["globally_unique_seed_flank_bridge"])
        self.assertFalse(report["region_attributable_bridge"])
        self.assertEqual(report["region_attributable_seed_support_pairs"], 0)

    def test_region_filter_does_not_hide_other_seed_bridge(self):
        result = audit_mask_read_support(
            {("S", "R"): REGION},
            {("S", "R"): SEED, ("S", "R2"): SEED},
            [(SEED, "NNNN")], report_region="R")
        self.assertEqual(len(result["mask_runs"]), 1)
        report = result["mask_runs"][0]
        self.assertEqual(report["other_seed_bridges"], 1)
        self.assertFalse(report["region_attributable_bridge"])

    def test_other_seed_different_gap_is_not_same_bridge(self):
        result = audit_mask_read_support(
            {("S", "R"): REGION},
            {("S", "R"): SEED, ("S", "R2"): LEFT + "C" * 9 + RIGHT},
            [(SEED, "NNNN")])
        report = result["mask_runs"][0]
        self.assertEqual(report["other_seed_bridges"], 0)
        self.assertTrue(report["region_attributable_bridge"])

    def test_reverse_complement_allele_detection(self):
        read = reverse_complement(LEFT + ALT_ALLELE + RIGHT)
        self.assertEqual(spanning_alleles(read, LEFT, RIGHT, 8), {ALT_ALLELE})

    def test_low_quality_allele_not_counted_as_support(self):
        read = LEFT + ALT_ALLELE + RIGHT
        quality = "I" * len(LEFT) + "I!" + "I" * (len(ALT_ALLELE) - 2 + len(RIGHT))
        report = audit_mask_read_support(
            {("S", "R"): REGION}, {("S", "R"): SEED},
            [((read, quality), ("NNNN", "IIII"))], min_base_quality=20)["mask_runs"][0]
        self.assertEqual(report["exact_bridge_pairs"], 0)
        self.assertEqual(report["low_quality_bridge_pairs"], 1)
        self.assertEqual(report["alternative_support_pairs"], 0)

    def test_quality_filter_reverse_complement_and_flanks(self):
        read = LEFT + SEED_ALLELE + RIGHT
        self.assertEqual(spanning_alleles(
            reverse_complement(read), LEFT, RIGHT, 8,
            "I" * len(read), 20), {SEED_ALLELE})
        quality = "!" + "I" * (len(read) - 1)
        self.assertEqual(spanning_alleles(
            reverse_complement(read), LEFT, RIGHT, 8,
            quality[::-1], 20), set())

    def test_quality_required_when_filtering(self):
        with self.assertRaisesRegex(ValueError, "qualities required"):
            spanning_alleles(SEED, LEFT, RIGHT, 8, min_base_quality=20)
        with self.assertRaisesRegex(ValueError, "between 0 and 93"):
            spanning_alleles(SEED, LEFT, RIGHT, 8, min_base_quality=94)

    def test_fastq_includes_original_phred_qualities(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "r1.fastq", Path(tmp) / "r2.fastq"
            p1.write_text("@r/1\\nACGT\\n+\\nI!II\\n".replace("\\n", "\n"))
            p2.write_text("@r/2\\nTGCA\\n+\\nIIII\\n".replace("\\n", "\n"))
            self.assertEqual(list(fastq_pairs(p1, p2, include_quality=True)),
                             [(("ACGT", "I!II"), ("TGCA", "IIII"))])

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
