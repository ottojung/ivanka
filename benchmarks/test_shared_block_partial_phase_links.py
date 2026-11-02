"""Focused synthetic tests for direct partial-block phase linkage."""
import unittest
from shared_block_partial_phase_links import audit_partial_links
from test_shared_block_phase_links import fixture, pair


class PartialPhaseTests(unittest.TestCase):
    def test_complete_block_is_linked_only_when_observed(self):
        masked, refs = fixture()
        result = audit_partial_links(masked, refs,
                                     pair("one", "x", refs["one"]), 8, 100)
        levels = result["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["3"]["read_pair_ids"], 1)
        self.assertEqual(levels["1"]["read_pair_ids"], 1)

    def test_last_base_does_not_impute_other_block_bases(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"], start=102, mate_start=250)
        rows[0]["seq"] = refs["one"][102:202]
        rows[0]["qual"] = "I"*100
        rows[0]["cigar"] = "100M"
        result = audit_partial_links(masked, refs, rows, 8, 100)
        levels = result["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["read_pair_ids"], 1)
        self.assertEqual(levels["3"]["read_pair_ids"], 0)

    def test_unobserved_insert_never_links(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I"*65
        rows[0]["cigar"] = "65M"
        result = audit_partial_links(masked, refs, rows, 8, 100)
        levels = result["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["read_pair_ids"], 0)

    def test_duplicate_sequences_not_independent(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"]) + pair("one", "y", refs["one"])
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["3"]["read_pair_ids"], 2)
        self.assertEqual(levels["3"]["distinct_pair_sequences"], 1)

    def test_same_sequence_with_low_quality_does_not_count_distinct(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"]) + pair("one", "y", refs["one"])
        rows[2]["qual"] = "!"*150
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["3"]["read_pair_ids"], 1)
        self.assertEqual(levels["3"]["distinct_pair_sequences"], 0)

    def test_partial_marker_conflict_is_observed_not_assigned(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"], start=102, mate_start=250)
        rows[0]["seq"] = refs["one"][102:202]
        rows[0]["qual"] = "I"*100
        rows[0]["cigar"] = "100M"
        # A real observed alternative marker allele, not a reference imputation.
        rows[0]["seq"] = rows[0]["seq"][:78] + "G" + rows[0]["seq"][79:]
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["observed_linkages"][0]["marker_base"], "G")
        self.assertEqual(levels["3"]["read_pair_ids"], 0)

    def test_conflicting_mates_fail_closed(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"], start=80, mate_start=95)
        rows[1]["seq"] = "G"*150
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["3"]["read_pair_ids"], 0)

    def test_secondary_pair_is_ignored(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"])
        rows[0]["flag"] = "355"
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["read_pair_ids"], 0)

    def test_upstream_marker_requires_observed_prefix(self):
        masked, refs = fixture()
        for name, seq in list(refs.items()):
            refs[name] = seq[:80] + ("A" if name in ("one", "three") else "G") + seq[81:]
        # The existing downstream marker also remains; select upstream -20.
        rows = pair("one", "x", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:101]
        rows[0]["qual"] = "I"*21
        rows[0]["cigar"] = "21M"
        result = audit_partial_links(masked, refs, rows, 8, 100)
        upstream = next(m for m in result["markers"]
                        if m["offset_from_block_start"] == -20)
        levels = upstream["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["read_pair_ids"], 1)
        self.assertEqual(levels["3"]["read_pair_ids"], 0)

    def test_conflicting_marker_calls_do_not_link(self):
        masked, refs = fixture()
        rows = pair("one", "x", refs["one"], start=80, mate_start=170)
        rows[1]["seq"] = "G"*150
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["1"]["read_pair_ids"], 0)

    def test_reverse_reference(self):
        masked, refs = fixture()
        comp = str.maketrans("ACGT","TGCA")
        refs["four"] = refs["four"].translate(comp)[::-1]
        rows = pair("four", "rev", refs["four"], start=205, mate_start=30)
        levels = audit_partial_links(masked, refs, rows, 8, 100)["markers"][0]["linkage_by_observed_edge_length"]
        self.assertEqual(levels["3"]["read_pair_ids"], 1)
        self.assertEqual(levels["3"]["observed_linkages"][0]["marker_base"], "G")


if __name__ == "__main__":
    unittest.main()
