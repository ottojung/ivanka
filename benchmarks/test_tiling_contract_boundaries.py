"""Boundary contracts for reference-free contig tiling."""

import unittest

from ivanka_read_tiling import K, tile_supported_contig


class TilingBoundaries(unittest.TestCase):
    def test_length_at_span_is_untouched(self):
        seq = "ACGT" * 500
        self.assertEqual(tile_supported_contig((">x", seq), [3] * (len(seq)-K+1)), [(">x", seq)])

    def test_small_remainder_cannot_produce_tiny_tile(self):
        for n in (2001, 2111, 2399):
            with self.subTest(n=n):
                seq = "A" * n
                self.assertEqual(tile_supported_contig((">x", seq), [3] * (n-K+1)), [(">x", seq)])

    def test_minimum_allowed_second_tile_is_retained(self):
        seq = "ACGT" * 600
        result = tile_supported_contig((">x", seq), [3] * (len(seq)-K+1))
        self.assertEqual([len(s) for _, s in result], [1200, 1200])

    def test_too_many_tiles_remain_unsplit(self):
        seq = "A" * 66000
        self.assertEqual(tile_supported_contig((">x", seq), [3] * (len(seq)-K+1)), [(">x", seq)])

    def test_missing_31mer_depth_is_rejected(self):
        with self.assertRaises(ValueError):
            tile_supported_contig((">x", "A"*3500), [3]*3500)

    def test_invalid_parameters_fail_closed(self):
        seq = "A" * 3600
        depth = [3] * (len(seq)-K+1)
        for options in ({"span": 30}, {"span": 100001}, {"overlap": -1},
                        {"overlap": 2000}, {"min_coverage": -0.1},
                        {"min_coverage": 1.1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                tile_supported_contig((">x", seq), depth, **options)
