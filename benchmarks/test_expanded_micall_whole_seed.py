"""Read evidence, not hidden truth, determines MiCall's evaluated full seed."""
import csv
import tempfile
import unittest
from pathlib import Path

from expanded.micall_whole_seed import select_whole_seed, evaluate_whole_seed
from benchmarks.test_expanded_micall_dominant import HXB2_PREFIX, write


def write_whole(folder, contents):
    with (Path(folder) / "conseq_all.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "sample", "seed", "region", "q-cutoff", "consensus-percent-cutoff",
            "seed-offset", "region-offset", "sequence"))
        writer.writeheader()
        for seed, sequence in contents.items():
            writer.writerow({"sample": "test", "seed": seed,
                             "region": "", "q-cutoff": 15,
                             "consensus-percent-cutoff": "MAX",
                             "seed-offset": 0, "region-offset": "",
                             "sequence": sequence})


class MiCallWholeSeedTests(unittest.TestCase):
    def test_full_final_seed_not_short_project_consensus(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 350}, {"strong": HXB2_PREFIX[:15]})
            write_whole(folder, {"strong": HXB2_PREFIX})
            result = select_whole_seed(folder)
            self.assertEqual(result["sequence"], HXB2_PREFIX)
            self.assertEqual(result["short_region_length"], 15)
            self.assertEqual(result["whole_seed_length"], len(HXB2_PREFIX))
            self.assertEqual(result["support"], 350)
            truth = Path(folder) / "truth.fa"
            truth.write_text(">HXB2_fragment\n" + HXB2_PREFIX + "\n")
            scored = evaluate_whole_seed(
                {"nominal_fractions": [1.0]}, truth, folder)
            self.assertEqual(scored["score"], 1.0)
            self.assertTrue(scored["dominant_exact"])
            self.assertEqual(len(scored["source"]["whole_seed_conseq_sha256"]), 64)

    def test_supported_not_truth_matching_seed_is_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 500, "weak": 15}, {
                "strong": "C" * len(HXB2_PREFIX), "weak": HXB2_PREFIX})
            write_whole(folder, {"strong": "C" * len(HXB2_PREFIX),
                                 "weak": HXB2_PREFIX})
            truth = Path(folder) / "truth.fa"
            truth.write_text(">HXB2_fragment\n" + HXB2_PREFIX + "\n")
            result = evaluate_whole_seed(
                {"nominal_fractions": [1.0]}, truth, folder)
            self.assertEqual(result["source"]["region"], "strong")
            self.assertEqual(result["source"]["support"], 500)
            self.assertLess(result["score"], 1.0)
            self.assertFalse(result["dominant_exact"])

    def test_whole_seed_missing_or_duplicated_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 42}, {"strong": HXB2_PREFIX[:10]})
            with self.assertRaisesRegex(ValueError, "missing"):
                select_whole_seed(folder)
            write_whole(folder, {"other": HXB2_PREFIX})
            with self.assertRaisesRegex(ValueError, "unique"):
                select_whole_seed(folder)
            write_whole(folder, {"strong": HXB2_PREFIX})
            path = Path(folder) / "conseq_all.csv"
            lines = path.read_text().splitlines()
            path.write_text("\n".join(lines + [lines[-1]]) + "\n")
            with self.assertRaisesRegex(ValueError, "unique"):
                select_whole_seed(folder)

    def test_short_region_can_contain_micall_unresolved_x(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 40}, {"strong": "ACGxTX"})
            write_whole(folder, {"strong": HXB2_PREFIX})
            result = select_whole_seed(folder)
            self.assertEqual(result["short_region_length"], 6)
            self.assertEqual(result["whole_seed_length"], len(HXB2_PREFIX))

    def test_micall_x_unresolved_is_valid_but_not_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, {"strong": 40}, {"strong": HXB2_PREFIX[:10]})
            write_whole(folder, {"strong": HXB2_PREFIX[:12] + "X" + HXB2_PREFIX[13:]})
            result = select_whole_seed(folder)
            self.assertIn("X", result["sequence"])
            truth = Path(folder) / "truth.fa"
            truth.write_text(">HXB2_fragment\n" + HXB2_PREFIX + "\n")
            scored = evaluate_whole_seed({"nominal_fractions": [1.0]}, truth, folder)
            self.assertLess(scored["score"], 1.0)
            self.assertFalse(scored["dominant_exact"])


if __name__ == "__main__":
    unittest.main()
