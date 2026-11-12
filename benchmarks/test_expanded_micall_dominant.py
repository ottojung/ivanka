"""End-to-end scorer chooses MiCall output using reads, never hidden truth."""
import csv
import tempfile
import unittest
from pathlib import Path

from expanded.micall_dominant import (evaluate_final_dominant,
                                     select_final_dominant)
from expanded.score import score_sequences

# Short HXB2 K03455.1 prefix: a parser/scoring fixture, not a new genome.
HXB2_PREFIX = ("TGGAAGGGCTAATTCACTCCCAACGAAGACAAGATATCCT"
               "TGATCTGTGGATCTACCACA")


def write(folder, counts, rows):
    target = Path(folder)
    with (target / "conseq.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "sample", "region", "q-cutoff", "consensus-percent-cutoff",
            "offset", "sequence"))
        writer.writeheader()
        for region, sequence in rows.items():
            writer.writerow({"sample": "test", "region": region,
                             "q-cutoff": 15, "consensus-percent-cutoff": "MAX",
                             "offset": 0, "sequence": sequence})
    with (target / "remap_counts.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "sample", "type", "count", "filtered_count", "seed_dist",
            "other_dist", "other_seed"))
        writer.writeheader()
        for region, count in counts.items():
            writer.writerow({"sample": "test", "type": "remap-final " + region,
                             "count": count})


class MiCallFinalDominantTests(unittest.TestCase):
    def test_read_support_determines_dominance_not_truth_similarity(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 900, "weak": 25}, {
                "strong": "C"*len(HXB2_PREFIX),
                "weak": HXB2_PREFIX,
            })
            selected = select_final_dominant(folder)
            self.assertEqual(selected["region"], "strong")
            self.assertEqual(selected["support"], 900)
            self.assertEqual(selected["sequence"], "C"*len(HXB2_PREFIX))
            self.assertEqual(selected["final_max_regions"], 2)
            self.assertEqual(len(selected["conseq_csv_sha256"]), 64)
            self.assertEqual(len(selected["remap_counts_sha256"]), 64)

    def test_unresolved_micall_x_stays_valid_but_not_perfect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, {"main": 44},
                  {"main": HXB2_PREFIX[:18] + "xX" + HXB2_PREFIX[20:]})
            selected = select_final_dominant(root)
            self.assertIn("XX", selected["sequence"])
            truth = root / "known-hxb2-fragment.fasta"
            truth.write_text(">HXB2_prefix\n" + HXB2_PREFIX + "\n")
            report = evaluate_final_dominant(
                {"nominal_fractions": [1.0]}, truth, root)
            self.assertLess(report["score"], 1.0)
            self.assertFalse(report["dominant_exact"])

    def test_final_micall_dominant_can_be_scored_after_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, {"main": 48}, {"main": HXB2_PREFIX})
            truth = root / "hxb2-prefix.fasta"
            truth.write_text(">HXB2_K03455_prefix\n" + HXB2_PREFIX + "\n")
            report = evaluate_final_dominant(
                {"nominal_fractions": [1.0]}, truth, root)
            self.assertEqual(report["score"], 1.0)
            self.assertTrue(report["dominant_exact"])
            self.assertEqual(report["source"]["region"], "main")
            self.assertEqual(report["score_origin"],
                             "micall_final_dominant_truth_v1")

    def test_empty_micall_output_fails_even_if_assembler_exited_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"main": 0}, {"main": ""})
            with self.assertRaisesRegex(ValueError, "no final MAX"):
                select_final_dominant(folder)

    def test_support_from_different_sample_cannot_select_winner(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"main": 32}, {"main": HXB2_PREFIX})
            path = Path(folder) / "remap_counts.csv"
            path.write_text(path.read_text().replace(
                "test,remap-final", "someone-else,remap-final"))
            with self.assertRaisesRegex(ValueError, "another sample"):
                select_final_dominant(folder)

    def test_missing_final_remap_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"unrelated": 17}, {"main": HXB2_PREFIX})
            with self.assertRaisesRegex(ValueError, "lacks original-read support"):
                select_final_dominant(folder)

    def test_unknown_or_duplicate_max_regions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"main": 32}, {"main": HXB2_PREFIX})
            target = Path(folder) / "conseq.csv"
            lines = target.read_text().splitlines()
            target.write_text("\n".join(lines + [lines[-1]])+"\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                select_final_dominant(folder)

    def test_equal_support_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"z": 44, "a": 44},
                  {"z": HXB2_PREFIX, "a": HXB2_PREFIX})
            selected = select_final_dominant(folder)
            self.assertTrue(selected["equal_support_ambiguous"])
            self.assertEqual(selected["region"], "a")

    def test_standalone_diagnostic_helper_is_not_pipeline_attestation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "truth.fasta"
            p.write_text(">hxb2\n" + HXB2_PREFIX + "\n")
            score = score_sequences({"nominal_fractions": [1.0]},
                                    p, [HXB2_PREFIX])
            self.assertEqual(score["score"], 1)
            self.assertNotIn("score_origin", score)


if __name__ == "__main__":
    unittest.main()
