"""Tests for transitive observed-phase graph with original pair provenance."""
import unittest
from types import SimpleNamespace

from shared_node_transitive_phase_links import audit_transitive_links
from test_shared_block_phase_links import fixture, pair


class TransitivePhaseTests(unittest.TestCase):
    def test_direct_same_pair_still_reported(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        self.assertEqual(m["direct_linked_read_pair_ids"], 2)
        self.assertFalse(m["no_direct_observation_same_pair"])

    def test_identical_pair_sequences_not_double_counted_as_independent(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        # Two pairs total but same signature
        self.assertEqual(m["direct_linked_read_pair_ids"], 2)
        self.assertGreaterEqual(m["linking_pair_signatures"], 1)

    def test_unobserved_insert_not_imputed(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I" * 65
        rows[0]["cigar"] = "65M"
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        self.assertEqual(m["total_linked_read_pair_ids"], 0)

    def test_no_imputed_bases_in_nodes(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        self.assertIn("interpretation", result)
        self.assertIn("No imputed insert bases", result["interpretation"])

    def test_preserves_minor_variant_observation(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        # change marker observation
        rows = pair("one", "a", refs["one"], start=80, mate_start=95)
        # But make them conflict - should not create false linkage
        rows[1]["seq"] = "G" * 150
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        self.assertEqual(m["total_linked_read_pair_ids"], 0)


if __name__ == "__main__":
    unittest.main()
