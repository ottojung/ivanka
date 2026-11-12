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

    def test_full_seed_conseq_all_uses_real_final_remap_support(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, {"seed-strong": 100, "seed-weak": 4}, {})
            with (root / "conseq_all.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=(
                    "sample", "seed", "region", "q-cutoff",
                    "consensus-percent-cutoff", "sequence"))
                writer.writeheader()
                for seed, seq in (("seed-strong", HXB2_PREFIX),
                                  ("seed-weak", "C"*len(HXB2_PREFIX))):
                    writer.writerow({"sample": "test", "seed": seed,
                                     "region": "", "q-cutoff": 15,
                                     "consensus-percent-cutoff": "MAX",
                                     "sequence": seq})
            selected = select_final_dominant(root)
            self.assertEqual(selected["region"], "seed-strong")
            self.assertEqual(selected["source_output"], "conseq_all.csv")
            self.assertEqual(selected["support"], 100)
            self.assertEqual(selected["sequence"], HXB2_PREFIX)

    def test_nonremapped_final_seed_is_not_a_false_dominant_genome(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, {"observed": 100}, {})
            with (root / "conseq_all.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=(
                    "sample", "seed", "region", "q-cutoff",
                    "consensus-percent-cutoff", "sequence"))
                writer.writeheader()
                for seed in ("observed", "unattributed"):
                    writer.writerow({"sample": "test", "seed": seed,
                                     "region": "", "q-cutoff": 15,
                                     "consensus-percent-cutoff": "MAX",
                                     "sequence": HXB2_PREFIX})
            result = select_final_dominant(root)
            self.assertEqual(result["region"], "observed")
            self.assertEqual(result["unattributed_final_candidates"], 1)
            (root / "remap_counts.csv").write_text(
                "sample,type,count\ntest,raw,100\n")
            with self.assertRaisesRegex(ValueError, "read-support"):
                select_final_dominant(root)

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
                             "micall_final_dominant_truth_v2")

    def test_micall_masked_unknown_positions_are_penalized_not_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            masked = HXB2_PREFIX[:15] + "X"*8 + HXB2_PREFIX[23:]
            write(root, {"main": 84}, {"main": masked})
            selection = select_final_dominant(root)
            self.assertEqual(selection["sequence"], masked)
            self.assertEqual(selection["support"], 84)
            truth = root / "truth.fasta"
            truth.write_text(">HXB2-prefix\n" + HXB2_PREFIX + "\n")
            result = evaluate_final_dominant(
                {"nominal_fractions": [1.0]}, truth, root)
            self.assertGreater(result["score"], 0)
            self.assertLess(result["score"], 1)
            self.assertFalse(result["dominant_exact"])
            self.assertEqual(result["source"]["support"], 84)

    def test_truly_illegal_micall_consensus_symbols_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"main": 84}, {"main": HXB2_PREFIX + "Z"})
            with self.assertRaisesRegex(ValueError, "invalid final MiCall"):
                select_final_dominant(folder)

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
