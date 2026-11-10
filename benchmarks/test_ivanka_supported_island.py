"""Read-derived island extraction for fragmentary or overextended contigs."""
import unittest

from ivanka_trim_unsupported import K, trim_supported_island


class ReadIslandTests(unittest.TestCase):
    def test_prefers_broader_dense_island(self):
        seq = "ACGT" * 1500
        depth = [0] * (len(seq) - K + 1)
        depth[350:1150] = [10] * 800
        depth[3200:4600] = [6] * 1400
        entry = (">candidate", seq)
        result = trim_supported_island(entry, depth)
        self.assertEqual(result[0], entry[0])
        self.assertEqual(result[1], seq[2688:5142])

    def test_keeps_complete_dense_candidate(self):
        seq = "ACGT" * 400
        depth = [10] * (len(seq) - K + 1)
        self.assertEqual(trim_supported_island((">x", seq), depth),
                         (">x", seq))

    def test_conservative_terminal_clipping_takes_precedence(self):
        seq = "A" * 2800 + "CGT" * 450
        depth = [0] * 2800 + [10] * (len(seq) - K + 1 - 2800)
        result = trim_supported_island((">x",seq),depth)
        self.assertEqual(result[1],seq[2288:])

    def test_declines_when_no_large_dense_interval(self):
        seq = "ACGT" * 1600
        depth = [3 if i % 4 == 0 else 0
                 for i in range(len(seq) - K + 1)]
        self.assertEqual(trim_supported_island((">x",seq),depth),
                         (">x",seq))

    def test_rejects_mismatched_depth(self):
        with self.assertRaises(ValueError):
            trim_supported_island((">x","A"*1300),[0]*14)


if __name__ == "__main__":
    unittest.main()
