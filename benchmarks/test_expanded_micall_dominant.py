"""Final MiCall alignment uses the exact local reference-panel algorithm."""
import csv
import tempfile
import unittest
from pathlib import Path

from benchmarks.project_references import final_max_sequences
from benchmarks.reference_panel import best_panel_alignment
from expanded.micall_dominant import evaluate_final_alignment, SCORE_ORIGIN
from expanded.score import read_fasta, reference_truth, score_sequences

HXB2_PREFIX = ("TGGAAGGGCTAATTCACTCCCAACGAAGACAAGATATCCT"
               "TGATCTGTGGATCTACCACA")


def write(folder, rows):
    with (Path(folder) / "conseq.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "sample", "region", "q-cutoff", "consensus-percent-cutoff",
            "offset", "sequence"))
        writer.writeheader()
        for region, sequence in rows.items():
            writer.writerow({"sample": "test", "region": region,
                             "q-cutoff": 15, "consensus-percent-cutoff": "MAX",
                             "offset": 0, "sequence": sequence})


class LocalAlignmentTests(unittest.TestCase):
    def test_synthetic_and_physical_use_identical_local_alignment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = HXB2_PREFIX
            write(root, {"wrong": "C" * len(expected),
                         "correct": expected})
            truth = root/"truth.fa"
            truth.write_text(">truth\n" + expected + "\n")
            report = evaluate_final_alignment(
                {"nominal_fractions": [1.]}, truth, root)
            physical_algorithm = best_panel_alignment(
                final_max_sequences(root), (("truth", expected),))
            self.assertEqual(report["score"], physical_algorithm["score"])
            self.assertEqual(report["score"], len(expected))
            self.assertEqual(report["score_origin"], SCORE_ORIGIN)
            self.assertEqual(report["source"]["reference_count"], 1)
            self.assertEqual(report["source"]["final_max_contig_count"], 2)
            self.assertEqual(len(report["source"]["conseq_csv_sha256"]), 64)

    def test_local_alignment_does_not_normalize_to_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            truth = root/"truth.fa"
            truth.write_text(">truth\n" + HXB2_PREFIX + "\n")
            fragment = HXB2_PREFIX[:25]
            write(root, {"region": fragment})
            result = evaluate_final_alignment(
                {"nominal_fractions": [1.]}, truth, root)
            self.assertEqual(result["score"], 25.)
            self.assertFalse(result["dominant_exact"])

    def test_panel_is_exactly_one_dominant_generating_sequence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root/"truth.fa"
            reference.write_text(">minor\n" + "C"*40 + "\n>major\n" +
                                 HXB2_PREFIX + "\n")
            manifest = {"nominal_fractions": [.1, .9]}
            self.assertEqual(reference_truth(manifest, reference), HXB2_PREFIX)
            write(root, {"region": HXB2_PREFIX})
            result = evaluate_final_alignment(manifest, reference, root)
            self.assertEqual(result["score"], len(HXB2_PREFIX))
            manifest["nominal_fractions"] = [.9, .1]
            self.assertEqual(reference_truth(manifest, reference), "C"*40)

    def test_empty_final_micall_fails_without_fabricated_score(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            truth = root/"truth.fa"
            truth.write_text(">truth\n" + HXB2_PREFIX + "\n")
            with self.assertRaisesRegex(ValueError, "missing final MiCall"):
                evaluate_final_alignment(
                    {"nominal_fractions": [1.]}, truth, root)

    def test_final_output_digest_is_source_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            truth = root/"truth.fa"
            truth.write_text(">truth\n" + HXB2_PREFIX + "\n")
            write(root, {"region": HXB2_PREFIX})
            result = evaluate_final_alignment(
                {"nominal_fractions": [1.]}, truth, root)
            import hashlib
            self.assertEqual(result["source"]["conseq_csv_sha256"],
                             hashlib.sha256((root/"conseq.csv").read_bytes())
                             .hexdigest())
            self.assertEqual(result["source"]["source_output"], "conseq.csv")

    def test_standalone_scoring_uses_exact_same_local_function(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            truth = root/"truth.fa"
            truth.write_text(">truth\n" + HXB2_PREFIX + "\n")
            assembled = [HXB2_PREFIX[:32], "C"*10]
            actual = score_sequences({"nominal_fractions": [1.]},
                                     truth, assembled)
            expected = best_panel_alignment(
                assembled, (("truth", HXB2_PREFIX),))
            self.assertEqual(actual["score"], expected["score"])
            self.assertNotIn("score_origin", actual)
            self.assertEqual(read_fasta(truth), [HXB2_PREFIX])


if __name__ == "__main__":
    unittest.main()
