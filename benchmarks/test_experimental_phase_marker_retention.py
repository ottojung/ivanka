"""Focused CPU-only tests for conservative final-MAX phase-marker accounting."""
import unittest

from experimental_phase_marker_retention import (
    audit_phase_markers, canonical_kmers,
)


class PhaseMarkerAuditTests(unittest.TestCase):
    def test_reverse_complement_and_case_are_equivalent(self):
        self.assertEqual(canonical_kmers("AAGC", 4), {"AAGC"})
        self.assertEqual(canonical_kmers("gctt", 4), {"AAGC"})

    def test_masked_and_iupac_windows_never_count(self):
        self.assertEqual(canonical_kmers("AAAxxCCCCNggg", 3),
                         {"AAA", "CCC"})
        self.assertEqual(canonical_kmers("ACGN", 4), set())

    def test_reject_invalid_sizes_and_region_changes(self):
        with self.assertRaises(ValueError):
            canonical_kmers("AAAA", 0)
        with self.assertRaises(ValueError):
            audit_phase_markers({"A": "AAAA"}, {"B": "AAAA"})
        with self.assertRaises(ValueError):
            audit_phase_markers({}, {})
        with self.assertRaises(ValueError):
            audit_phase_markers({"A": "AAAA"}, {"A": "AAAA"}, (3, 3))

    def test_loss_in_one_region_is_visible_even_if_other_retains_it(self):
        result = audit_phase_markers(
            {"A": "AAACCC", "B": "AAAGGG"},
            {"A": "NNNCCC", "B": "AAAGGG"}, (3,))
        audit = result["sizes"]["3"]
        self.assertEqual(audit["pooled_lost"], 2)  # AAC, ACC
        self.assertEqual(audit["regions"]["A"]["lost"], 3)
        self.assertEqual(audit["regions"]["A"]["region_unique_lost"], 2)
        self.assertFalse(audit["all_baseline_region_markers_retained"])

    def test_identical_and_extended_alleles_have_no_lost_markers(self):
        result = audit_phase_markers(
            {"A": "ACGTxxxACGT", "B": "TTTCCC"},
            {"A": "ACGTAAAACGT", "B": "TTTCCC"}, (3, 4))
        for audit in result["sizes"].values():
            self.assertEqual(audit["pooled_lost"], 0)
            self.assertTrue(audit["all_baseline_region_markers_retained"])
        self.assertGreater(result["sizes"]["3"]["pooled_gained"], 0)

    def test_unique_baseline_markers_track_their_own_region(self):
        result = audit_phase_markers(
            {"A": "AAAAC", "B": "GGGGT"},
            {"A": "GGGGT", "B": "AAAAC"}, (5,))
        audit = result["sizes"]["5"]
        self.assertEqual(audit["pooled_lost"], 0)
        self.assertEqual(audit["regions"]["A"]["region_unique_lost"], 1)
        self.assertEqual(audit["regions"]["B"]["region_unique_lost"], 1)
        self.assertFalse(audit["all_baseline_region_markers_retained"])


if __name__ == "__main__":
    unittest.main()
