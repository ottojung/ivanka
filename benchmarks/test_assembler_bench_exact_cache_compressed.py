"""Compressed-only exact-coverage sidecars keep their verified evidence."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    import compressed_tables as ct
except ModuleNotFoundError:
    from benchmarks import compressed_tables as ct

from benchmarks.assembler_bench import exact_cache


def track_values():
    values = {
        "length": 2, "mean": 2.0, "median": 2.0,
        "minimum": 1.0, "maximum": 3.0,
        "zero_count": 0, "zero_fraction": 0.0, "longest_zero_run": 0,
        "breadth_ge_1": 1.0, "breadth_ge_3": 0.5,
        "breadth_ge_10": 0.0, "breadth_ge_100": 0.0,
        "depth_profile": [2.0, 2.0],
        "quantiles": {"p10": 1.0, "p25": 1.5, "p50": 2.0,
                      "p75": 2.5, "p90": 3.0},
    }
    return values


class ExactCacheCompressedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        self.cohort, self.sample, self.tool = "synthetic", "S001", "ivanka"
        self.folder = exact_cache.sidecar(
            self.cache, self.cohort, self.sample, self.tool)
        self.folder.mkdir(parents=True)
        self.coverage = self.folder / "exact_coverage.csv"
        self.coverage.write_text(
            "contig,position,exact_coverage,exact_coverage_overlapped\n"
            "longest_MAX,1,3,2\nlongest_MAX,2,1,2\n")
        self.source_digest, self.image = "a" * 64, "b" * 64
        report = {
            "source_conseq_sha256": self.source_digest,
            "source_image_sha256": self.image,
            "overlap_size": 70,
            "exact_coverage_sha256": ct.logical_digest(self.coverage)[0],
            "micall_exact_coverage_module_sha256": exact_cache.SOURCE_SHA256,
            "method": "micall-longest-final-MAX-exact-v2",
            "source_fastq_sha256": ["c" * 64, "d" * 64],
            "selected_sequence_sha256": "e" * 64,
            "bases": 2,
            "tracks": {"exact_coverage": track_values(),
                       "exact_coverage_overlapped": track_values()},
        }
        (self.folder / "provenance.json").write_text(
            json.dumps(report, sort_keys=True))

    def append(self):
        return exact_cache.append(
            {}, self.cache, self.cohort, self.sample, self.tool,
            self.source_digest, self.image)

    def test_compressed_only_sidecar_matches_plain_evidence(self):
        plain, plain_evidence = self.append()
        self.assertIsNotNone(plain_evidence)
        compressed_path = ct.compress_table(self.coverage)
        self.assertTrue(compressed_path.is_file())
        self.assertFalse(self.coverage.exists())
        compressed, compressed_evidence = self.append()
        self.assertEqual(compressed, plain)
        self.assertEqual(compressed_evidence, plain_evidence)


if __name__ == "__main__":
    unittest.main()
