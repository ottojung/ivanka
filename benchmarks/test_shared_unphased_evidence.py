"""Proof guards for redacted, original-pair shared-local observations."""
import json
import unittest
from unittest.mock import patch

from shared_unphased_evidence import build_shared_evidence
from test_shared_block_phase_links import fixture, pair


class SharedUnphasedEvidenceTests(unittest.TestCase):
    def test_redacted_by_default_no_phase_or_independent_molecules(self):
        masked, refs = fixture()
        rows = pair("one", "private-id-a", refs["one"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        encoded = json.dumps(result)
        self.assertFalse(result["raw_qnames_included"])
        self.assertNotIn("private-id-a", encoded)
        self.assertFalse(result["full_length_haplotype_phase_inferred"])
        self.assertFalse(result["independent_molecules_inferred"])
        self.assertFalse(result["insert_bases_imputed"])
        self.assertTrue(all(not n["is_phased"] for n in result["nodes"]))
        self.assertGreater(result["strict_original_read_pair_ids_evaluated"], 0)

    def test_opt_in_original_qname_provenance(self):
        masked, refs = fixture()
        rows = pair("one", "private-id-a", refs["one"])
        result = build_shared_evidence(
            masked, refs, rows, anchor=8, radius=100,
            include_qnames=True)
        self.assertTrue(result["raw_qnames_included"])
        self.assertIn("private-id-a", result["original_qname_provenance"])
        self.assertTrue(all("original_qnames" in n for n in result["nodes"]))

    def test_duplicate_complete_pairs_count_signature_once(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        block = [n for n in result["nodes"] if n["feature_kind"] == "block"]
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["original_read_pair_ids"], 2)
        self.assertEqual(block[0]["distinct_consistent_pair_sequence_signatures"], 1)

    def test_partial_duplicate_signature_withheld_from_distinct_support(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        rows[2]["qual"] = "!"*len(rows[2]["qual"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        block = [n for n in result["nodes"] if n["feature_kind"] == "block"]
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["original_read_pair_ids"], 1)
        self.assertEqual(block[0]["distinct_consistent_pair_sequence_signatures"], 0)

    def test_contradictory_alleles_cannot_count_as_two_distinct_pairs(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        # Force a same-signature collision across conflicting original
        # marker observations, to exercise the conservative aggregation.
        with patch("shared_unphased_evidence._pair_signature",
                   return_value=("same-sequence", "same-sequence")):
            result = build_shared_evidence(masked, refs, rows, 8, 100)
        markers = [n for n in result["nodes"]
                   if n["feature_kind"] == "marker"]
        self.assertEqual({n["observed_allele"] for n in markers}, {"A", "G"})
        self.assertTrue(all(
            n["distinct_consistent_pair_sequence_signatures"] == 0
            for n in markers))

    def test_unobserved_insert_cannot_create_marker_evidence(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I"*65
        rows[0]["cigar"] = "65M"
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        self.assertFalse(result["insert_bases_imputed"])
        self.assertFalse(any(n["feature_kind"] == "marker"
                             for n in result["nodes"]))

    def test_bad_search_parameter_fails_closed(self):
        masked, refs = fixture()
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], anchor=0)
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], minimum_quality=-1)
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], include_qnames="yes")

    def test_repeated_qname_is_not_a_strict_original_pair(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) * 2
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        self.assertEqual(result["strict_original_read_pair_ids_evaluated"], 0)
        self.assertEqual(result["nodes"], [])


if __name__ == "__main__":
    unittest.main()
