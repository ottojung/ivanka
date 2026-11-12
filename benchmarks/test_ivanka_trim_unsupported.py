"""Regression tests for optional end-clipping based on original read pairs."""
import unittest
from ivanka_trim_unsupported import K, trim_terminal_unsupported, trim_supported_island


class ReadTrimTests(unittest.TestCase):
    def test_uncovered_long_prefix(self):
        seq = "A"*2800 + "CGT"*450
        depth = [0]*2800 + [10]*(len(seq)-K+1-2800)
        got = trim_terminal_unsupported((">sample",seq),depth)
        self.assertEqual(got[0],">sample")
        self.assertEqual(got[1],seq[2288:])

    def test_uncovered_long_suffix(self):
        seq = "CGT"*450 + "A"*2800
        depth = [9]*(1350-K+1) + [0]*(len(seq)-1350)
        got = trim_terminal_unsupported((">sample",seq),depth)
        self.assertEqual(got[1],seq[:1862])

    def test_sparse_sites_not_clipped(self):
        seq = "A"*4100
        depth = [0]*2800 + [1]*(4100-K+1-2800)
        self.assertEqual(trim_terminal_unsupported((">x",seq),depth),
                         (">x",seq))

    def test_scattered_sites_not_clipped(self):
        seq = "A"*4100
        depth = [0]*2800 + [3 if i%4==0 else 0
                            for i in range(4100-K+1-2800)]
        self.assertEqual(trim_terminal_unsupported((">x",seq),depth),
                         (">x",seq))

    def test_short_terminal_is_preserved(self):
        seq = "A"*1600
        depth = [0]*200 + [3]*(1600-K+1-200)
        self.assertEqual(trim_terminal_unsupported((">x",seq),depth),
                         (">x",seq))

    def test_few_sites_not_clipped(self):
        seq = "A"*4000
        depth = [0]*3200 + [3]*200 + [0]*(4000-K+1-3400)
        self.assertEqual(trim_terminal_unsupported((">x",seq),depth),
                         (">x",seq))

    def test_depth_length_must_match(self):
        with self.assertRaises(ValueError):
            trim_terminal_unsupported((">x","A"*100),[0]*3)


if __name__=="__main__":
    unittest.main()


class TrimBoundsTests(unittest.TestCase):
    def test_prefix_trim_returns_exact_original_depth_offset(self):
        seq = "A"*2800 + "CGT"*1000
        depth = [0]*2800 + [10]*(len(seq)-K+1-2800)
        trimmed, start, end = trim_terminal_unsupported((">x",seq), depth, with_bounds=True)
        self.assertEqual(trimmed[1], seq[start:end])
        self.assertEqual((start,end), (2288,len(seq)))
        self.assertEqual(len(depth[start:end-K+1]), len(trimmed[1])-K+1)

    def test_supported_island_bounds_cover_retained_segment(self):
        seq = "A"*2800 + "CGT"*1000
        depth = [0]*2800 + [10]*(len(seq)-K+1-2800)
        trimmed, start, end = trim_supported_island((">x",seq), depth, with_bounds=True)
        self.assertEqual(trimmed[1], seq[start:end])
