"""Focused CPU-only tests for shared-block consensus safety gates."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import sys

from shared_block_consensus_candidate import (
    candidate_from_calls, canonical_base, audit_remap, _strict_pair,
)


class SharedBlockCandidateTests(unittest.TestCase):
    def test_exactly_100_distinct_qnames_can_qualify(self):
        calls = [(i, f"q{j}", b) for i, b in enumerate("ACGT")
                 for j in range(100)]
        r = candidate_from_calls("ACGT", calls)
        self.assertTrue(r["eligible"])
        self.assertEqual(r["read_derived_candidate"], "ACGT")

    def test_99_is_not_100(self):
        r = candidate_from_calls("A", [(0, str(i), "A") for i in range(99)])
        self.assertFalse(r["eligible"])
        self.assertIsNone(r["read_derived_candidate"])

    def test_same_qname_on_four_targets_counts_once(self):
        calls = [(0, str(i), "A") for i in range(100) for _ in range(4)]
        r = candidate_from_calls("A", calls)
        self.assertEqual(r["positions"][0]["depth_qnames"], 100)

    def test_conflicting_mates_are_excluded_not_majority_voted(self):
        calls = [(0, str(i), "A") for i in range(100)]
        calls.extend([(0, "0", "G"), (0, "0", "A")])
        r = candidate_from_calls("A", calls)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["positions"][0]["conflicting_qnames"], 1)
        self.assertEqual(r["positions"][0]["depth_qnames"], 99)

    def test_70_alternatives_preserved_in_spectrum(self):
        calls = [(0, f"a{i}", "A") for i in range(203)]
        calls += [(0, f"g{i}", "G") for i in range(70)]
        r = candidate_from_calls("A", calls)
        self.assertTrue(r["eligible"])
        self.assertEqual(r["positions"][0]["allele_qnames"]["G"], 70)

    def test_100_alternatives_prevent_collapsing_supported_variant(self):
        calls = [(0, f"a{i}", "A") for i in range(203)]
        calls += [(0, f"g{i}", "G") for i in range(100)]
        self.assertFalse(candidate_from_calls("A", calls)["eligible"])

    def test_read_majority_must_match_shared_seed(self):
        calls = [(0, f"g{i}", "G") for i in range(150)]
        calls += [(0, f"a{i}", "A") for i in range(20)]
        r = candidate_from_calls("A", calls)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["positions"][0]["read_major_base"], "G")

    def test_tie_rejected(self):
        calls = [(0, f"a{i}", "A") for i in range(100)]
        calls += [(0, f"g{i}", "G") for i in range(100)]
        self.assertFalse(candidate_from_calls("A", calls)["eligible"])

    def test_one_unsupported_position_blocks_whole_allele(self):
        calls = [(0, str(i), "A") for i in range(100)]
        self.assertIsNone(candidate_from_calls("AC", calls)["read_derived_candidate"])

    def test_empty_or_ambiguous_seed_rejected(self):
        for allele in ("", "AN", "Ax"):
            with self.assertRaises(ValueError):
                candidate_from_calls(allele, [])

    def test_bad_observation_rejected(self):
        for call in ((-1, "q", "A"), (1, "q", "A"), (0, "", "A"),
                     (0, "q", "N")):
            with self.assertRaises(ValueError):
                candidate_from_calls("A", [call])

    def test_reverse_orientation(self):
        self.assertEqual(canonical_base("T", "T", "A"), "A")
        self.assertEqual(canonical_base("G", "G", "C"), "C")
        self.assertEqual(canonical_base("G", "A", "A"), "G")
        with self.assertRaises(ValueError):
            canonical_base("A", "G", "A")

    def test_no_input_mutation(self):
        calls = [(0, "q", "A")]
        snapshot = calls[:]
        candidate_from_calls("A", calls)
        self.assertEqual(calls, snapshot)

    def pair(self, name="q", rname="one"):
        return [dict(rname=rname, qname=name, flag="99", pos="1",
                     pnext="8", rnext="=", base="A"),
                dict(rname=rname, qname=name, flag="147", pos="8",
                     pnext="1", rnext="=", base="A")]

    def test_sam_wrapper_filters_secondary_and_duplicate(self):
        fake = SimpleNamespace(
            group_loci=lambda masked, refs: ("A", {"one": {5: (0, "A")}}),
            sam_observations=lambda row, coords, minimum_quality:
                [(0, row["base"], row["qname"], "A")])
        rows = self.pair("good")
        for flag in (0x100, 0x400, 0x800, 0x4):
            bad = self.pair(f"bad{flag}")
            bad[0]["flag"] = str(99 | flag)
            rows += bad
        rows += self.pair("three") + [self.pair("three")[0]]
        rows += self.pair("singleton")[:1]
        with patch.dict(sys.modules, {"shared_locus_remap_coverage": fake}):
            r = audit_remap(None, {"one": "A"}, rows, required_depth=1)
        self.assertEqual(r["positions"][0]["depth_qnames"], 1)

    def test_sam_wrapper_detects_reverse_locus(self):
        fake = SimpleNamespace(
            group_loci=lambda masked, refs: ("A", {"one": {5: (0, "T")}}),
            sam_observations=lambda row, coords, minimum_quality:
                [(0, "T", row["qname"], "T")])
        with patch.dict(sys.modules, {"shared_locus_remap_coverage": fake}):
            r = audit_remap(None, {"one": "A"}, self.pair(), required_depth=1)
        self.assertTrue(r["eligible"])

    def test_mate_geometry_and_flags_fail_closed(self):
        good = self.pair()
        self.assertTrue(_strict_pair(good))
        for key, value in (("pnext", "999"), ("rname", "other"),
                           ("flag", "83"), ("rnext", "other")):
            rows = [dict(r) for r in good]
            rows[0][key] = value
            self.assertFalse(_strict_pair(rows), key)
        self.assertFalse(_strict_pair(good[:1]))

    def test_same_signed_tlen_is_not_rejected(self):
        rows = self.pair()
        for row in rows:
            row["tlen"] = "100"
        self.assertTrue(_strict_pair(rows))


if __name__ == "__main__":
    unittest.main()
