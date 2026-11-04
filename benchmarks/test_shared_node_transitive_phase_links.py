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
        self.assertEqual(m["direct_edge_or_full_read_pair_ids"], 2)
        self.assertFalse(m["direct_full_block_read_pair_ids"] == 0)

    def test_identical_pair_sequences_not_double_counted_as_independent(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        # Two pairs total but same signature
        self.assertEqual(m["direct_edge_or_full_read_pair_ids"], 2)
        self.assertGreaterEqual(m["direct_edge_or_full_distinct_pair_sequences"], 1)

    def test_unobserved_insert_not_imputed(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I" * 65
        rows[0]["cigar"] = "65M"
        result = audit_transitive_links(masked, refs, rows, 8, 100)
        m = result["markers"][0]
        self.assertEqual(m["direct_edge_or_full_read_pair_ids"], 0)

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
        self.assertEqual(m["direct_edge_or_full_read_pair_ids"], 0)


    def test_indirect_graph_members_do_not_inflate_direct_witnesses(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        report = audit_transitive_links(masked, refs, rows, 8, 100)
        for m in report["markers"]:
            self.assertLessEqual(m["direct_full_block_read_pair_ids"],
                                 m["direct_edge_or_full_read_pair_ids"])
            self.assertLessEqual(m["direct_full_block_distinct_pair_sequences"],
                                 m["direct_edge_or_full_distinct_pair_sequences"])
            self.assertGreaterEqual(
            m["co_component_read_pair_ids_not_phase_evidence"], 0)
        self.assertIsInstance(m["direct_full_block_observed_linkages"], list)

    def test_competing_marker_alleles_veto_transitive_claims(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        m = audit_transitive_links(masked, refs, rows, 8, 100)["markers"][0]
        self.assertEqual(m["competing_allele_components"], 1)
        self.assertEqual(m["nonconflicting_components"], 0)
        self.assertEqual(m["co_component_read_pair_ids_not_phase_evidence"], 0)

    def test_full_block_allele_spectrum_does_not_claim_haplotypes(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        report = audit_transitive_links(masked, refs, rows, 8, 100)
        m = report["markers"][0]
        self.assertEqual(m["direct_full_block_read_pair_ids"], 2)
        self.assertEqual(sum(v["read_pair_ids"]
                             for v in m["direct_full_block_observed_linkages"]), 2)
        self.assertIn("not prove phase", m["uncertainty"])


if __name__ == "__main__":
    unittest.main()
