"""Focused tests for conservative direct phase-marker linkage."""
import random
import unittest
from types import SimpleNamespace

from shared_block_phase_links import discover_markers, audit_links

COMP = str.maketrans("ACGT", "TGCA")


def fixture():
    rng = random.Random(17)
    seq = "".join(rng.choice("ACGT") for _ in range(410))
    refs = {}
    for name, base in (("one", "A"), ("two", "G"), ("three", "A"), ("four", "G")):
        refs[name] = seq[:180] + base + seq[181:]
    masked = SimpleNamespace(sequence=seq[:100] + "xxx" + seq[103:],
                             start=100, end=103)
    return masked, refs


def pair(ref, qname, reference, start=80, mate_start=250):
    return [
        {"qname": qname, "rname": ref, "rnext": "=", "flag": "99",
         "pos": str(start + 1), "pnext": str(mate_start + 1),
         "seq": reference[start:start + 150], "qual": "I" * 150,
         "cigar": "150M"},
        {"qname": qname, "rname": ref, "rnext": "=", "flag": "147",
         "pos": str(mate_start + 1), "pnext": str(start + 1),
         "seq": reference[mate_start:mate_start + 150], "qual": "I" * 150,
         "cigar": "150M"},
    ]


class PhaseLinksTests(unittest.TestCase):
    def test_unique_flanked_snp_discovered(self):
        masked, refs = fixture()
        allele, loci, markers = discover_markers(masked, refs, 8, 100)
        self.assertEqual(len(allele), 3)
        self.assertEqual(len(loci), 4)
        self.assertEqual([m["offset"] for m in markers], [80])
        self.assertEqual(markers[0]["alleles"], {
            "one": "A", "two": "G", "three": "A", "four": "G"})

    def test_same_pair_directly_links_full_block_to_marker(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        result = audit_links(masked, refs, rows, 8, 100)
        marker = result["markers"][0]
        self.assertEqual(result["complete_block_pair_ids"], 2)
        self.assertEqual(marker["marker_observed_pair_ids"], 2)
        self.assertEqual(marker["linked_read_pair_ids"], 2)
        self.assertEqual(marker["linked_distinct_pair_sequences"], 2)
        self.assertEqual({x["marker_base"] for x in marker["observed_linkages"]},
                         {"A", "G"})

    def test_duplicate_pair_sequences_do_not_inflate_linkage(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        marker = audit_links(masked, refs, rows, 8, 100)["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 2)
        self.assertEqual(marker["linked_distinct_pair_sequences"], 1)

    def test_partial_duplicate_signature_does_not_count_as_distinct(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        rows[2]["qual"] = "!" * 150
        result = audit_links(masked, refs, rows, 8, 100)
        marker = result["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 1)
        self.assertEqual(marker["linked_distinct_pair_sequences"], 0)

    def test_indel_disrupts_shared_marker_coordinate(self):
        masked, refs = fixture()
        refs["four"] = refs["four"][:150] + "AAAAAA" + refs["four"][150:]
        _, _, markers = discover_markers(masked, refs, 8, 100)
        self.assertEqual(markers, [])

    def test_unobserved_insert_is_not_linkage(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I" * 65
        rows[0]["cigar"] = "65M"
        marker = audit_links(masked, refs, rows, 8, 100)["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 0)

    def test_conflicting_mate_observation_blocks_linkage(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=95)
        rows[1]["seq"] = "G" * 150
        marker = audit_links(masked, refs, rows, 8, 100)["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 0)

    def test_malformed_or_secondary_pair_ignored(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        rows[0]["flag"] = "355"
        marker = audit_links(masked, refs, rows, 8, 100)["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 0)

    def test_reverse_reference_uses_canonical_marker_base(self):
        masked, refs = fixture()
        refs["four"] = refs["four"].translate(COMP)[::-1]
        _, _, markers = discover_markers(masked, refs, 8, 100)
        self.assertEqual(markers[0]["alleles"]["four"], "G")

    def test_reverse_target_direct_linkage(self):
        masked, refs = fixture()
        refs["four"] = refs["four"].translate(COMP)[::-1]
        rows = pair("four", "rev", refs["four"], start=205, mate_start=30)
        result = audit_links(masked, refs, rows, 8, 100)
        marker = result["markers"][0]
        self.assertEqual(marker["linked_read_pair_ids"], 1)
        self.assertEqual(marker["observed_linkages"][0]["marker_base"], "G")

    def test_repeat_marker_flanks_are_rejected(self):
        masked, refs = fixture()
        for k, seq in refs.items():
            refs[k] = seq + seq[172:189]
        _, _, markers = discover_markers(masked, refs, 8, 100)
        self.assertEqual(markers, [])

    def test_invalid_search_parameters_fail(self):
        masked, refs = fixture()
        with self.assertRaises(ValueError):
            discover_markers(masked, refs, 0, 100)


if __name__ == "__main__":
    unittest.main()
