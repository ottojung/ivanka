"""Q15 per-qname coverage protection tests for experimental reallocation."""
import unittest

from experimental_depth_guard import observed_positions, initial_depth
from experimental_single_placement import reallocate
from test_experimental_single_placement import REFS, SOURCE, pair


class DepthGuardTests(unittest.TestCase):
    def test_overlapping_mates_count_once_per_qname(self):
        old = pair("a") + pair("b")
        depth = initial_depth(old, REFS)
        self.assertEqual(depth[("src", 11)], 2)
        self.assertEqual(depth[("src", 4)], 2)

    def test_exact_100_blocks_reallocation(self):
        old = [r for n in range(100) for r in pair(str(n))]
        new, stats = reallocate(old, REFS, "forward", protect_depth=100)
        self.assertEqual(new, old)
        self.assertEqual(stats["moved_pairs"], 0)
        self.assertEqual(stats["rejections"]["protected_source_depth"], 100)

    def test_already_below_100_blocks_reallocation(self):
        old = [r for n in range(99) for r in pair(str(n))]
        new, stats = reallocate(old, REFS, "forward", protect_depth=100)
        self.assertEqual(new, old)
        self.assertEqual(stats["moved_pairs"], 0)

    def test_101_allows_only_one_move(self):
        old = [r for n in range(101) for r in pair(str(n))]
        new, stats = reallocate(old, REFS, "forward", protect_depth=100)
        self.assertEqual(stats["moved_pairs"], 1)
        self.assertEqual([r["rname"] for r in new[:2]], ["forward", "forward"])
        self.assertEqual([r["rname"] for r in new[2:]], ["src"]*200)

    def test_softclip_and_quality_filter(self):
        row = dict(pair()[0], cigar="1S12M", pos="5", seq="A"+SOURCE[4:16],
                   qual="!"+("I"*12))
        self.assertEqual(observed_positions(row, SOURCE), set(range(4,16)))

    def test_reject_malformed_cigar(self):
        row = dict(pair()[0], cigar="12M")
        with self.assertRaises(ValueError):
            observed_positions(row, SOURCE)

    def test_unmapped_micall_mate_has_zero_coverage(self):
        unmapped = dict(pair()[0], flag="133", cigar="*")
        self.assertEqual(observed_positions(unmapped, SOURCE), set())
        self.assertEqual(initial_depth([unmapped], REFS), {})

    def test_mapped_missing_cigar_and_unmapped_alignment_fail_closed(self):
        mapped_missing = dict(pair()[0], cigar="*")
        unmapped_aligned = dict(pair()[0], flag="133")
        for invalid in (mapped_missing, unmapped_aligned):
            with self.assertRaises(ValueError):
                observed_positions(invalid, SOURCE)

    def test_invalid_protection_depth(self):
        with self.assertRaises(ValueError):
            reallocate(pair(), REFS, "forward", protect_depth=0)


if __name__ == "__main__":
    unittest.main()
