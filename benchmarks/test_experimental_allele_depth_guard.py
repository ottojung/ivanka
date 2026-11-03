"""Allele-aware protection regression tests for experimental single-placement remap."""
import unittest
from collections import Counter

from experimental_depth_guard import (
    initial_depth, observed_alleles, protected_move,
)
from experimental_single_placement import reallocate
from test_experimental_single_placement import REFS, SOURCE, pair


class AlleleAwareDepthTests(unittest.TestCase):
    def test_mismatching_read_does_not_inflate_reference_depth(self):
        original = [r for n in range(100) for r in pair(str(n))]
        variant = pair("variant")
        alt = "T" if SOURCE[4] != "T" else "A"
        variant[0]["seq"] = alt + variant[0]["seq"][1:]
        depth = initial_depth(original + variant, REFS)
        self.assertEqual(depth[("src", 4)], 100)
        self.assertEqual(depth[("src", 11)], 101)
        candidate, stats = reallocate(original + variant, REFS, "forward",
                                      protect_depth=100)
        self.assertEqual(candidate, original + variant)
        self.assertEqual(stats["moved_pairs"], 0)

    def test_overlapping_mate_conflict_excludes_pair_at_site(self):
        original = [r for n in range(101) for r in pair(str(n))]
        conflict = pair("conflict")
        alt = "A" if SOURCE[11] != "A" else "C"
        conflict[1]["seq"] = alt + conflict[1]["seq"][1:]
        depth = initial_depth(original + conflict, REFS)
        self.assertEqual(depth[("src", 11)], 101)
        self.assertEqual(depth[("src", 4)], 102)

    def test_nonreference_source_pair_cannot_deplete_guard(self):
        variant = pair("variant")
        alt = "T" if SOURCE[4] != "T" else "A"
        variant[0]["seq"] = alt + variant[0]["seq"][1:]
        depth = Counter({("src", site): 150 for site in range(len(SOURCE))})
        self.assertFalse(protected_move(variant, "src", depth, REFS, 100))
        self.assertEqual(depth[("src", 4)], 150)

    def test_unmapped_and_low_quality_do_not_support_allele(self):
        row = dict(pair()[0], flag="133", cigar="*")
        self.assertEqual(observed_alleles(row, SOURCE), {})
        low = dict(pair()[0], qual="!"*13)
        self.assertEqual(observed_alleles(low, SOURCE), {})

    def test_reverse_orientation_uses_sam_reference_oriented_bases(self):
        from exact_pair_remap_equivalence import reverse_complement
        row = dict(pair()[0], seq=reverse_complement(pair()[0]["seq"]),
                   flag="83")
        # SAM SEQ must already be oriented to the reference; mismatches
        # cannot be mistaken for reference-allele coverage.
        depth = initial_depth([row], REFS)
        self.assertEqual(depth[("src", 5)], 0)


if __name__ == "__main__":
    unittest.main()
