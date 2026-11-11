"""Sequence conservation and support-based selection are strict invariants."""

import random
import unittest

from ivanka_read_tiling import K, tile_supported_contig


class TilingMetamorphic(unittest.TestCase):
    def test_randomized_exact_overlapping_partition(self):
        rng = random.Random(0x1911)
        for length in (2443, 3000, 4001, 6158, 7084, 9999, 15901):
            seq = "".join(rng.choices("ACGT", k=length))
            depth = [rng.randrange(3, 12) for _ in range(length-K+1)]
            for overlap in (0, 31, 512, 1000):
                with self.subTest(length=length, overlap=overlap):
                    tiles = tile_supported_contig((">x", seq), depth, overlap=overlap)
                    starts = [0]
                    if len(tiles) > 1:
                        n = len(tiles)
                        starts = [i*(length//n)+min(i,length%n) for i in range(n)]
                    for (header, part), start in zip(tiles, starts):
                        self.assertTrue(header.startswith(">x"))
                        self.assertEqual(part, seq[start:start+len(part)])
                    self.assertTrue(all(len(part)<=2000+overlap for _, part in tiles))

    def test_one_weak_tile_preserves_original(self):
        seq = "ACGT" * 1500
        depth = [4]*(len(seq)-K+1)
        depth[2000:4000] = [0]*2000
        self.assertEqual(tile_supported_contig((">x", seq), depth, overlap=512), [(">x",seq)])

    def test_does_not_mutate_original_inputs(self):
        entry = (">x", "ACGT" * 1500)
        depth = [3]*(len(entry[1])-K+1)
        before = depth.copy()
        tile_supported_contig(entry, depth, overlap=512)
        self.assertEqual(depth, before)

    def test_header_does_not_change_partition(self):
        seq = "ACGT" * 1500
        depth = [3]*(len(seq)-K+1)
        a = tile_supported_contig((">x", seq), depth, overlap=512)
        b = tile_supported_contig((">anything", seq), depth, overlap=512)
        self.assertEqual([s for _,s in a], [s for _,s in b])
