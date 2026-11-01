"""Focused tests for conservative seed-versus-region masking diagnostics."""
import csv
import random
from pathlib import Path
import tempfile
import unittest

from consensus_mask_stage_audit import (
    audit, canonical_kmers, exact_flank_correspondence, kmer_stage_retention,
    mask_runs, max_rows, reverse_complement,
)


class MaskStageTests(unittest.TestCase):
    def test_canonical_kmers_are_reverse_complement_invariant(self):
        sequence = "ACGTGCTATCGATGCAGGTCACATGTTACGATCGAGTCATG"
        self.assertEqual(canonical_kmers(sequence, 7),
                         canonical_kmers(reverse_complement(sequence), 7))
        self.assertEqual(canonical_kmers("ACNGTA", 3),
                         canonical_kmers("ACNGTA".lower(), 3))
        self.assertEqual(canonical_kmers("ACNGTA", 3),
                         canonical_kmers("GTA", 3))
        with self.assertRaises(ValueError):
            canonical_kmers(sequence, 0)

    def test_masking_is_measured_as_sequence_loss_not_read_loss(self):
        randomizer = random.Random(84)
        seed = "".join(randomizer.choices("ACGT", k=500))
        final = seed[:180] + "X" * 50 + seed[230:]
        report = kmer_stage_retention(seed, final)
        for k in ("31", "101", "251"):
            self.assertGreater(report[k]["seed_unique"], 0)
            self.assertGreater(report[k]["seed_absent_from_final"], 0)
            self.assertEqual(report[k]["final_absent_from_seed"], 0)
        region = audit({("S", "R"): final}, {("S", "R"): seed})["regions"][0]
        self.assertEqual(region["canonical_kmer_stage_comparison"], report)
        self.assertIsNone(audit({("S", "R"): final}, {})["regions"][0]
                          ["canonical_kmer_stage_comparison"])

    def test_mask_runs(self):
        self.assertEqual(mask_runs("ACxxGXXXTa"), [(2, 4), (5, 8)])

    def test_unique_forward_bridge(self):
        seed = ("ACGT"*7 + "GTA") + "AACCGGTT" + ("TGCA"*7 + "CTG")
        region = ("ACGT"*7 + "GTA") + "x"*8 + ("TGCA"*7 + "CTG")
        self.assertEqual(exact_flank_correspondence(region.upper(), seed, 31, 39), ("+", 0))
        report = audit({("S", "R"): region}, {("S", "R"): seed}, 31)["regions"][0]
        self.assertEqual(report["final_masked_bases"], 8)
        self.assertEqual(report["seed_masked_bases"], 0)
        self.assertEqual(report["uniquely_exact_flank_bridged_bases"], 8)

    def test_reverse_orientation(self):
        oriented = ("ACGT"*7 + "GTA") + "AACCGGTT" + ("TGCA"*7 + "CTG")
        self.assertEqual(exact_flank_correspondence(
            ("ACGT"*7 + "GTA") + "X"*8 + ("TGCA"*7 + "CTG"), reverse_complement(oriented), 31, 39), ("-", 0))

    def test_ambiguous_repeat_not_certified(self):
        unit = ("ACGT"*7 + "GTA") + "AACCGGTT" + ("TGCA"*7 + "CTG")
        seed = unit + "ACACAC" + unit
        self.assertIsNone(exact_flank_correspondence(
            ("ACGT"*7 + "GTA") + "X"*8 + ("TGCA"*7 + "CTG"), seed, 31, 39))

    def test_short_or_ambiguous_flank(self):
        self.assertIsNone(exact_flank_correspondence("AAXXXTT", "AACGGTT", 2, 5, 3))
        self.assertIsNone(exact_flank_correspondence("AAAXXXNTTT", "AAACGGTTT", 3, 6, 3))

    def test_different_gap_length_not_certified(self):
        self.assertIsNone(exact_flank_correspondence(
            ("ACGT"*7 + "GTA") + "X"*7 + ("TGCA"*7 + "CTG"), ("ACGT"*7 + "GTA") + "AACCGGTT" + ("TGCA"*7 + "CTG"), 31, 38))

    def test_no_seed_row_is_reported_without_inference(self):
        item = audit({("S", "R"): "AxxT"}, {}, 2)["regions"][0]
        self.assertFalse(item["matching_seed_max_row"])
        self.assertIsNone(item["seed_masked_bases"])
        self.assertEqual(item["uniquely_exact_flank_bridged_runs"], 0)

    def test_csv_only_max_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conseq.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["sample", "region", "consensus-percent-cutoff", "sequence"])
                writer.writeheader()
                writer.writerow({"sample": "S", "region": "R", "consensus-percent-cutoff": "0.010", "sequence": "XXX"})
                writer.writerow({"sample": "S", "region": "R", "consensus-percent-cutoff": "MAX", "sequence": "ACx"})
            self.assertEqual(max_rows(path, "region"), {("S", "R"): "ACX"})
            with path.open("a", newline="") as handle:
                csv.writer(handle).writerow(["S", "R", "MAX", "ACX"])
            with self.assertRaisesRegex(ValueError, "duplicate MAX"):
                max_rows(path, "region")

    def test_invalid_anchor(self):
        with self.assertRaises(ValueError):
            audit({}, {}, 0)


if __name__ == "__main__":
    unittest.main()


class SeedRowSelectionTests(unittest.TestCase):
    def test_reference_region_rows_not_confused_with_seed_consensus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conseq_all.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "sample", "seed", "region", "consensus-percent-cutoff", "sequence"])
                writer.writeheader()
                writer.writerow({"sample": "S", "seed": "R", "region": "",
                                 "consensus-percent-cutoff": "MAX", "sequence": "ACGT"})
                writer.writerow({"sample": "S", "seed": "R", "region": "mapped-region",
                                 "consensus-percent-cutoff": "MAX", "sequence": "XXXX"})
            self.assertEqual(max_rows(path, "seed", seed_only=True), {("S", "R"): "ACGT"})
            with self.assertRaisesRegex(ValueError, "duplicate MAX"):
                max_rows(path, "seed")
