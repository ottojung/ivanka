"""CPU-only regression tests for direct full-block read-pair observations.

Full-block evidence is a stricter *diagnostic* than per-site pooled depth.
It is not 31bp-flank support or proof of long-range haplotype phase.
"""
import unittest

from shared_block_consensus_candidate import candidate_from_calls


def calls_for(pairs):
    for qname, allele in pairs.items():
        for site, base in enumerate(allele):
            if base != "-":
                yield (site, qname, base)


class CompleteBlockEvidenceTests(unittest.TestCase):
    def block(self, pairs, signatures=None):
        return candidate_from_calls(
            "ACG", list(calls_for(pairs)), required_depth=1,
            pair_signatures=signatures)["complete_block_observations"]

    def test_full_observation_is_not_assembled_from_different_pairs(self):
        block = self.block({"left": "A--", "middle": "-C-", "right": "--G"})
        self.assertEqual(block["complete_read_pair_ids"], 0)
        self.assertEqual(block["shared_allele_complete_read_pair_ids"], 0)

    def test_full_shared_and_alternative_alleles_are_separate(self):
        block = self.block({"seed": "ACG", "other": "ATG", "partial": "A-G"})
        self.assertEqual(block["complete_read_pair_ids"], 2)
        self.assertEqual(block["shared_allele_complete_read_pair_ids"], 1)
        self.assertEqual(block["alternative_complete_read_pair_ids"], 1)
        self.assertIsNone(block["distinct_pair_sequence_evidence"])

    def test_identical_pair_sequences_count_once(self):
        signatures = {"a": ("R1", "R2"), "b": ("R1", "R2")}
        block = self.block({"a": "ACG", "b": "ACG"}, signatures)
        distinct = block["distinct_pair_sequence_evidence"]
        self.assertEqual(block["shared_allele_complete_read_pair_ids"], 2)
        self.assertEqual(distinct["shared_allele_distinct_pair_sequences"], 1)
        self.assertEqual(distinct["complete_distinct_pair_sequences"], 1)

    def test_same_signature_discordant_full_alleles_excluded(self):
        signatures = {"a": ("R1", "R2"), "b": ("R1", "R2")}
        block = self.block({"a": "ACG", "b": "ATG"}, signatures)
        distinct = block["distinct_pair_sequence_evidence"]
        self.assertEqual(block["complete_read_pair_ids"], 2)
        self.assertEqual(distinct["complete_distinct_pair_sequences"], 0)
        self.assertEqual(distinct["ambiguous_or_partial_pair_sequences"], 1)

    def test_partial_mapping_invalidates_duplicate_full_signature(self):
        signatures = {"a": ("R1", "R2"), "b": ("R1", "R2")}
        block = self.block({"a": "ACG", "b": "A-G"}, signatures)
        distinct = block["distinct_pair_sequence_evidence"]
        self.assertEqual(block["complete_read_pair_ids"], 1)
        self.assertEqual(distinct["shared_allele_distinct_pair_sequences"], 0)
        self.assertEqual(distinct["ambiguous_or_partial_pair_sequences"], 1)

    def test_conflicting_mate_base_disqualifies_complete_pair(self):
        calls = list(calls_for({"a": "ACG"}))
        calls.append((1, "a", "T"))
        result = candidate_from_calls("ACG", calls, required_depth=1,
                                      pair_signatures={"a": ("R1", "R2")})
        block = result["complete_block_observations"]
        self.assertEqual(block["complete_read_pair_ids"], 0)
        self.assertEqual(block["distinct_pair_sequence_evidence"]
                         ["complete_distinct_pair_sequences"], 0)

    def test_empty_input_reports_no_full_block_support(self):
        block = self.block({})
        self.assertEqual(block["complete_read_pair_ids"], 0)
        self.assertEqual(block["alternative_complete_read_pair_ids"], 0)


if __name__ == "__main__":
    unittest.main()
