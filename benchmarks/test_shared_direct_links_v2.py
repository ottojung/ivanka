"""Versioned direct same-pair block-to-marker observations, never inferred phase."""
import json
import unittest
from unittest.mock import patch
from shared_unphased_evidence import build_shared_evidence
from test_shared_block_phase_links import fixture, pair


def report(rows, refs=None):
    masked, normal = fixture()
    return build_shared_evidence(masked, refs or normal, rows,
                                 anchor=8, radius=100,
                                 include_direct_links=True)


class DirectLinkageV2Tests(unittest.TestCase):
    def test_two_original_pairs_directly_link_complete_block_and_marker(self):
        _, refs = fixture()
        result = report(pair("one", "first", refs["one"]) +
                        pair("two", "second", refs["two"]))
        self.assertEqual(result["schema_version"],
                         "ivanka.shared_unphased_evidence_direct.v2")
        marker = result["marker_direct_links"][0]
        self.assertEqual(marker["direct_joint_observation_count"], 2)
        self.assertEqual(marker["direct_joint_distinct_pair_sequence_signatures"], 2)
        self.assertEqual({j["marker_allele"]
                          for j in marker["local_block_marker_observations"]},
                         {"A", "G"})
        self.assertFalse(marker["long_range_haplotype_phase_inferred"])
        self.assertEqual(result["phase_status"], "unidentified")
        self.assertFalse(result["raw_qnames_included"])
        self.assertNotIn("first", json.dumps(result))
        self.assertNotIn("second", json.dumps(result))

    def test_duplicates_never_inflate_sequence_signature_support(self):
        _, refs = fixture()
        x = report(pair("one", "a", refs["one"]) +
                   pair("one", "b", refs["one"]))["marker_direct_links"][0]
        self.assertEqual(x["direct_joint_observation_count"], 2)
        self.assertEqual(x["direct_joint_distinct_pair_sequence_signatures"], 1)
        self.assertEqual(x["local_block_marker_observations"][0][
            "consistent_distinct_pair_sequence_signatures"], 1)

    def test_partial_copy_vetoes_shared_sequence_signature(self):
        _, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        rows[2]["qual"] = "!" * 150
        x = report(rows)["marker_direct_links"][0]
        self.assertEqual(x["direct_joint_observation_count"], 1)
        self.assertEqual(x["direct_joint_distinct_pair_sequence_signatures"], 0)
        self.assertEqual(x["local_block_marker_observations"][0][
            "consistent_distinct_pair_sequence_signatures"], 0)

    def test_no_imputed_insert_or_full_block_phase(self):
        _, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I" * 65
        rows[0]["cigar"] = "65M"
        x = report(rows)["marker_direct_links"][0]
        self.assertEqual(x["direct_joint_observation_count"], 0)
        self.assertEqual(x["local_block_marker_observations"], [])

    def test_colliding_sequence_signature_with_conflicting_marker_fails_closed(self):
        _, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        with patch("shared_unphased_evidence._pair_signature",
                   return_value=("same", "sequence")):
            x = report(rows)["marker_direct_links"][0]
        self.assertEqual(x["direct_joint_observation_count"], 2)
        self.assertEqual(x["direct_joint_distinct_pair_sequence_signatures"], 0)
        self.assertTrue(all(j["consistent_distinct_pair_sequence_signatures"] == 0
                            for j in x["local_block_marker_observations"]))

    def test_v1_unchanged_when_extension_not_requested(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        v1 = build_shared_evidence(masked, refs, rows, 8, 100)
        v2 = build_shared_evidence(masked, refs, rows, 8, 100,
                                   include_direct_links=True)
        for key in ("marker_direct_links", "direct_linkage_observation_scope",
                    "direct_linkage_interpretation"):
            del v2[key]
        v2["schema_version"] = v1["schema_version"]
        self.assertEqual(v1, v2)


if __name__ == "__main__":
    unittest.main()
