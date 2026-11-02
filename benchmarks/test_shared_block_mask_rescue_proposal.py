"""Proof-oriented CPU-only tests for the guarded shared-local proposal."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shared_block_mask_rescue_proposal import propose_rescue


def evidence(n=100, distinct=100, site=True, candidate="AC",
             alternatives=None):
    return {
        "eligible": site,
        "sequence_diversity_guard_applied": True,
        "read_derived_candidate": candidate if site else None,
        "complete_block_observations": {
            "observed_complete_local_sequences": [
                {"sequence": "AC", "read_pair_ids": n,
                 "distinct_pair_sequences": distinct},
                *(alternatives or []),
            ],
        },
    }


class GuardedMaskRescueTests(unittest.TestCase):
    def setUp(self):
        self.masked = SimpleNamespace(sequence="GGxxTT", start=2, end=4)

    def run_case(self, report):
        with patch("shared_block_mask_rescue_proposal.audit_remap",
                   return_value=report):
            return propose_rescue(self.masked, {"one": "GACT"}, [])

    def test_exact_100_full_block_pairs_and_sequences(self):
        result = self.run_case(evidence())
        self.assertTrue(result["eligible"])
        self.assertEqual(result["proposed_region_sequence"], "GGACTT")
        self.assertEqual(self.masked.sequence, "GGxxTT")

    def test_99_full_block_pairs_rejected(self):
        self.assertFalse(self.run_case(evidence(n=99))["eligible"])

    def test_99_distinct_sequences_rejected(self):
        self.assertFalse(self.run_case(evidence(distinct=99))["eligible"])

    def test_per_position_gate_cannot_be_bypassed(self):
        self.assertFalse(self.run_case(evidence(site=False))["eligible"])

    def test_no_mosaic_if_majority_not_a_complete_allele(self):
        self.assertFalse(self.run_case(evidence(candidate="AG"))["eligible"])

    def test_supported_complete_alternative_blocks_rescue(self):
        alt = [{"sequence": "GC", "read_pair_ids": 100,
                "distinct_pair_sequences": 100}]
        self.assertFalse(self.run_case(evidence(alternatives=alt))["eligible"])

    def test_minor_allele_is_preserved_in_report(self):
        alt = [{"sequence": "GC", "read_pair_ids": 10,
                "distinct_pair_sequences": 10}]
        result = self.run_case(evidence(alternatives=alt))
        self.assertTrue(result["eligible"])
        self.assertEqual(result["alternative_complete_alleles"], alt)

    def test_not_even_one_nonmask_base_changed(self):
        self.masked.sequence = "aGxxTn"
        self.assertEqual(self.run_case(evidence())["proposed_region_sequence"],
                         "aGACTn")

    def test_nonexact_or_invalid_mask_rejected(self):
        for sequence, start, end in (("GGxNTT", 2, 4), ("GGxxTT", 2, 2),
                                     ("GGxxTT", -1, 4), ("GGxxTT", 2, 7),
                                     ("GGXXTT", 2, 4)):
            self.masked = SimpleNamespace(sequence=sequence, start=start, end=end)
            with self.assertRaises(ValueError):
                propose_rescue(self.masked, {}, [])

    def test_bad_threshold_rejected(self):
        with self.assertRaises(ValueError):
            propose_rescue(self.masked, {}, [], required_depth=0)
        with self.assertRaises(ValueError):
            propose_rescue(self.masked, {}, [], minimum_quality=-1)

    def test_strict_full_block_gate_even_if_sites_each_have_100(self):
        self.assertFalse(self.run_case(evidence(n=20, distinct=20))["eligible"])


if __name__ == "__main__":
    unittest.main()
