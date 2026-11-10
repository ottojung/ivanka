"""Read-only tiling preserves every base and rejects weak fragment support."""
import unittest

from ivanka_read_tiling import K, tile_supported_contig


class TilingTests(unittest.TestCase):
    def test_long_fully_supported_is_partitioned_without_loss(self):
        seq = "ACGT" * 1771
        depth = [4] * (len(seq) - K + 1)
        tiles = tile_supported_contig((">candidate", seq), depth, 2000)
        self.assertEqual([len(s) for _, s in tiles], [1771] * 4)
        self.assertEqual("".join(s for _, s in tiles), seq)
        self.assertEqual(len(set(h for h, _ in tiles)), 4)

    def test_too_short_remains_untouched(self):
        seq = "ACGT" * 600
        depth = [8] * (len(seq) - K + 1)
        self.assertEqual(tile_supported_contig((">x", seq), depth),
                         [(">x", seq)])

    def test_rejects_weak_tile_without_partial_output(self):
        seq = "A" * 6000
        depth = [5] * (len(seq) - K + 1)
        depth[2000:4000] = [0] * 2000
        self.assertEqual(tile_supported_contig((">x", seq), depth),
                         [(">x", seq)])

    def test_non_divisible_length_preserves_entire_sequence(self):
        seq = "ACGT" * 1000 + "T"
        d = [5] * (len(seq) - K + 1)
        result = tile_supported_contig((">x", seq), d, 2000)
        self.assertEqual("".join(s for _,s in result), seq)
        self.assertTrue(all(0 < len(s) <= 2000 for _,s in result))

    def test_mismatched_depth_fails_closed(self):
        with self.assertRaises(ValueError):
            tile_supported_contig((">x", "A"*4000), [1]*10)
