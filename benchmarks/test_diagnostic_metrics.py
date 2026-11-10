import csv
import tempfile
import unittest
from pathlib import Path

from diagnostic_metrics import extract, DIRECTIONS
from diagnostic_psi import compare_records


def write_csv(directory, name, header, rows):
    with (directory / name).open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


class DiagnosticMetricsTests(unittest.TestCase):
    def test_kive_semantics_and_multimapping_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_csv(folder, "genome_coverage.csv",
                      ["contig", "coverage", "concordance"],
                      [["sampleA", 10, 0.5], ["sampleB", 20, 0.9],
                       ["unknown-seed", 999, 0.0]])
            write_csv(folder, "nuc.csv",
                      ["seed", "refseq.nuc.pos", "clip"],
                      [["a", 10, 2], ["a", 10, 3],
                       ["b", 10, 4], ["a", 11, 0]])
            write_csv(folder, "exact_coverage.csv",
                      ["contig", "position", "exact_coverage",
                       "exact_coverage_overlapped"],
                      [["a", 1, 0, 0], ["a", 2, 1, 0],
                       ["a", 3, 5, 2]])
            write_csv(folder, "multimap_depth.csv",
                      ["refname", "position", "max_depth", "avg_depth"],
                      [["a", 1, 2, 1], ["b", 1, 1, 0.5]])
            write_csv(folder, "unique_aligned_fragments.csv",
                      ["unique_aligned_fragments"], [[8]])
            write_csv(folder, "remap_counts.csv",
                      ["type", "count"],
                      [["remap-fragments", 9], ["multimap-capped-pairs", 2]])
            actual = extract(folder)
            v = actual["values"]
            self.assertEqual(v["average_read_depth"], 15)
            self.assertEqual(v["total_read_depth"], 30)
            self.assertAlmostEqual(v["average_concordance"], 0.7)
            self.assertEqual(v["soft_clips_count"], 7)
            self.assertEqual(v["exact_uncovered_bases"], 1)
            self.assertEqual(v["exact_uncovered_overlapped_bases"], 2)
            self.assertAlmostEqual(v["exact_uncovered_fraction"], 1/3)
            self.assertEqual(v["multimap_max_depth_total"], 3)
            self.assertEqual(v["multimap_avg_depth_total"], 1.5)
            self.assertEqual(v["unique_aligned_fragments"], 8)
            self.assertEqual(v["mapped_fragments"], 9)
            self.assertEqual(v["multimap_capped_pairs"], 2)
            self.assertIsNone(v["multimap_oversized_pairs"])
            self.assertEqual(actual["errors"], [])
            self.assertEqual(actual["qualification_effect"], "none")

    def test_multi_contig_exact_csv_uses_longest_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_csv(Path(tmp), "exact_coverage.csv",
                      ["contig", "position", "exact_coverage"],
                      [["short", 1, 0], ["short", 2, 0],
                       ["long", 1, 0], ["long", 2, 1], ["long", 3, 2]])
            result = extract(tmp)
            self.assertEqual(result["values"]["exact_uncovered_bases"], 1)
            self.assertEqual(result["values"]["exact_uncovered_fraction"], 1/3)
            self.assertEqual(result["context"]["exact_coverage_selected_contig"],
                             "long")

    def test_absent_files_are_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = extract(tmp)
            self.assertTrue(all(x is None for x in actual["values"].values()))
            self.assertEqual(set(actual["unavailable"]), set(DIRECTIONS))

    def test_invalid_multimap_depth_is_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_csv(Path(tmp), "multimap_depth.csv",
                      ["refname", "position", "max_depth", "avg_depth"],
                      [["c", 1, 1, 2]])
            result = extract(tmp)
            self.assertIsNone(result["values"]["multimap_max_depth_total"])
            self.assertTrue(result["errors"])


class DiagnosticPsiTests(unittest.TestCase):
    def _record(self, name, left, right):
        return {
            "sample": name, "status": "finished",
            "iva": {"metrics": {"diagnostics": {"values": left}}},
            "ivanka": {"metrics": {"diagnostics": {"values": right}}},
        }

    def test_signed_direction_and_missing_are_not_qualification(self):
        pairs = [
            self._record("A", {"average_read_depth": 4,
                               "soft_clips_count": 8},
                         {"average_read_depth": 6,
                          "soft_clips_count": 5}),
            self._record("B", {"average_read_depth": 7,
                               "soft_clips_count": 10},
                         {"average_read_depth": 8,
                          "soft_clips_count": 9}),
        ]
        report = compare_records(pairs, expected_count=2)
        self.assertEqual(report["qualification_effect"], "none")
        for key in ("average_read_depth", "soft_clips_count"):
            metric = report["metrics"][key]
            self.assertEqual(metric["paired_samples"], 2)
            self.assertEqual(metric["psi"]["psi0"], 1.0)
            self.assertTrue(metric["psi"]["positive_all_nonnegative"])
        missing = report["metrics"]["exact_uncovered_bases"]
        self.assertEqual(missing["paired_samples"], 0)
        self.assertIsNone(missing["psi"])
        self.assertEqual(missing["missing_samples"], ["A", "B"])

    def test_missing_one_value_does_not_create_zero(self):
        report = compare_records([
            self._record("A", {"average_read_depth": 4},
                         {"average_read_depth": 6}),
            self._record("B", {"average_read_depth": 5},
                         {"average_read_depth": None}),
        ])
        self.assertEqual(report["metrics"]["average_read_depth"]["paired_samples"], 1)
        self.assertEqual(report["metrics"]["average_read_depth"]["missing_samples"], ["B"])

    def test_duplicate_samples_are_rejected(self):
        rec = self._record("A", {}, {})
        with self.assertRaises(ValueError):
            compare_records([rec, rec])


if __name__ == "__main__":
    unittest.main()
