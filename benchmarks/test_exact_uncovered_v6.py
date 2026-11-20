"""Exact-uncovered legacy catalog fields are strict source-attested aliases."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from assembler_bench import exact_cache


class UncoveredAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.name = "clonal-s012"
        self.tool = "iva"
        self.source = "a" * 64
        self.image = "b" * 64
        self.folder = exact_cache.sidecar(
            self.root, "synthetic", self.name, self.tool)
        self.folder.mkdir(parents=True)
        (self.folder / "exact_coverage.csv").write_text("source\n")
        self.evidence = {
            "source_conseq_sha256": self.source,
            "source_image_sha256": self.image,
            "exact_coverage_sha256": "c" * 64,
            "micall_exact_coverage_module_sha256": exact_cache.SOURCE_SHA256,
            "method": "micall-longest-final-MAX-exact-v2",
            "overlap_size": 70,
            "source_fastq_sha256": ["d" * 64, "e" * 64],
            "bases": 100,
            "selected_sequence_sha256": "f" * 64,
            "uncovered": 7,
            "tracks": {
                "exact_coverage": {
                    "zero_count": 7, "depth_profile": [0, 5]},
                "exact_coverage_overlapped": {
                    "zero_count": 13, "depth_profile": [0, 2]},
            },
        }
        self.aggregate = {
            "exact_coverage_zero_count": 7,
            "exact_coverage_zero_fraction": .07,
            "exact_coverage_length": 100,
            "exact_coverage_overlapped_length": 100,
            "exact_coverage_overlapped_zero_count": 13,
        }

    def append(self):
        (self.folder / "provenance.json").write_text(json.dumps(self.evidence))
        with patch.object(exact_cache, "values", return_value=self.aggregate),                 patch.object(exact_cache, "file_sha256",
                             return_value="c" * 64):
            return exact_cache.append(
                {"average_read_depth": 15}, self.root,
                "synthetic", self.name, self.tool, self.source, self.image)

    def test_all_three_legacy_uncovered_values_are_exact_aliases(self):
        result, profile = self.append()
        self.assertEqual(result["exact_uncovered_bases"], 7)
        self.assertEqual(result["exact_uncovered_fraction"], .07)
        self.assertEqual(result["exact_uncovered_overlapped_bases"], 13)
        self.assertEqual(result["average_read_depth"], 15)
        self.assertEqual(profile["full_span"], [0, 5])
        self.assertEqual(profile["inner_70"], [0, 2])

    def test_disagreeing_report_uncovered_count_is_rejected(self):
        self.evidence["uncovered"] = 8
        with self.assertRaisesRegex(ValueError, "uncovered counts disagree"):
            self.append()

    def test_disagreeing_consensus_length_is_rejected(self):
        self.evidence["bases"] = 99
        with self.assertRaisesRegex(ValueError, "uncovered counts disagree"):
            self.append()

    def test_missing_sidecar_does_not_invent_zero(self):
        row, profile = exact_cache.append(
            {}, self.root, "synthetic", "missing",
            self.tool, self.source, self.image)
        self.assertIsNone(profile)
        self.assertNotIn("exact_uncovered_bases", row)


if __name__ == "__main__":
    unittest.main()
