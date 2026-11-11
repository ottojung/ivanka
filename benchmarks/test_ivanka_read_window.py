"""Exact support-window regression tests; no benchmark reference permitted."""
import unittest
from ivanka_read_window import K, dominant_read_window


class WindowTests(unittest.TestCase):
    def test_prefers_original_pair_abundance(self):
        import random
        seq = "".join(random.Random(7 + i).choice("ACGT") for i in range(4000))
        depth = [3] * (len(seq) - K + 1)
        depth[1800:2500] = [20] * 700
        result = dominant_read_window((">x", seq), depth, 1200)
        self.assertEqual(result[0], ">x")
        self.assertEqual(len(result[1]), 1200)
        self.assertEqual(result[1], seq[1330:2530])

    def test_short_complete_sequence_unchanged(self):
        seq = "ACGT" * 100
        d = [4] * (len(seq)-K+1)
        self.assertEqual(dominant_read_window((">x", seq), d, 1000),
                         (">x", seq))

    def test_no_support_keeps_contig(self):
        seq = "A" * 4000
        d = [0] * (len(seq)-K+1)
        self.assertEqual(dominant_read_window((">x", seq), d),
                         (">x", seq))

    def test_ties_prefer_leftmost(self):
        seq = "ACGT" * 1000
        d = [4] * (len(seq)-K+1)
        self.assertEqual(dominant_read_window((">x", seq), d, 2000),
                         (">x", seq[:2000]))

    def test_rejects_malformed_depth(self):
        with self.assertRaises(ValueError):
            dominant_read_window((">x", "A"*4000), [1]*40)

    def test_rejects_invalid_width(self):
        seq = "A" * 4000
        d = [2] * (len(seq)-K+1)
        with self.assertRaises(ValueError):
            dominant_read_window((">x", seq), d, 20)
