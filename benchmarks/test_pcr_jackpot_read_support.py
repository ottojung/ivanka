"""Tests for the post-assembly read-support diagnostic."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from pcr_jackpot_read_support import compare, evaluate, read_support


class PCRJackpotReadSupportTest(unittest.TestCase):
    def test_counts_only_truth_observed_in_reads(self):
        result = compare({"a", "b", "c", "d"}, Counter(a=3, b=1, c=5, e=4),
                         {"a", "d", "e"}, {"b", "c", "d", "e"})
        self.assertEqual(result, {
            "truth_kmers_in_reads": 3, "candidate_raw_supported": 1,
            "rival_raw_supported": 2, "rival_only_supported_by_reads": 2,
            "rival_only_supported_by_3_distinct_read_strings": 1,
        })

    def test_repeated_reads_are_not_distinct_strings(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / name for name in ("r1.fq", "r2.fq")]
            for path in paths:
                path.write_text(("@r\n" + "A" * 31 + "\n+\n" + "!" * 31 + "\n") * 4)
            self.assertEqual(read_support(paths, {"A" * 31}), Counter({"A" * 31: 1}))
            paths[1].write_text("")
            with self.assertRaises(ValueError):
                read_support(paths, {"A" * 31})

    def test_incomplete_cohort_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "results.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                evaluate(root, root, root)
