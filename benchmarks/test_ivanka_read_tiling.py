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
        seq = "ACGT" * 500
        depth = [8] * (len(seq) - K + 1)
        self.assertEqual(tile_supported_contig((">x", seq), depth),
                         [(">x", seq)])

    def test_s75_length_can_be_tiled_without_losing_sequence(self):
        seq = "ACGT" * 610 + "ACG"
        self.assertEqual(len(seq), 2443)
        d = [5] * (len(seq) - K + 1)
        tiles = tile_supported_contig((">S75", seq), d, 2000)
        self.assertEqual([len(s) for _,s in tiles], [1222, 1221])
        self.assertEqual("".join(s for _,s in tiles), seq)

    def test_barely_over_span_is_not_split_into_tiny_fragments(self):
        seq = "A" * 2200
        d = [4] * (len(seq) - K + 1)
        self.assertEqual(tile_supported_contig((">x", seq), d, 2000),
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

    def test_overlap_retains_long_range_context_and_all_bases(self):
        seq = "ACGT" * 1539 + "AC"
        d = [5] * (len(seq) - K + 1)
        parts = tile_supported_contig((">x", seq), d, 2000, overlap=512)
        self.assertEqual(len(parts), 4)
        base, extra = divmod(len(seq), len(parts))
        start = 0
        for i, (_, part) in enumerate(parts):
            end = start + base + (i < extra)
            self.assertEqual(part, seq[start:min(len(seq), end + 512)])
            start = end
        self.assertEqual(start, len(seq))

    def test_invalid_overlap_fails_closed(self):
        seq = "A" * 4000
        with self.assertRaises(ValueError):
            tile_supported_contig((">x", seq), [4] * (len(seq)-K+1),
                                  overlap=2000)
