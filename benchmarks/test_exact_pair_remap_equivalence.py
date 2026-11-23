"""Proof-oriented unit tests for exact paired-template compatibility."""
import unittest
from exact_pair_remap_equivalence import (
    compatible_copies, lift_pair, reverse_complement, unique_placement,
    verified_source_references, pooled_site_calls,
)

TEMPLATE = "ACGTACCTGCAATGACCTGA"
SOURCE = "GGGG" + TEMPLATE + "TTTT"
FORWARD = "CCCC" + TEMPLATE + "AAAA"
REVERSE = "CCCC" + reverse_complement(TEMPLATE) + "AAAA"


def pair(source="src", seq=SOURCE):
    # Read-pair footprint is exactly TEMPLATE, with overlapping mates.
    a = dict(qname="pair1", flag="99", rname=source, pos="5", mapq="1",
             cigar="13M", rnext="=", pnext="12", tlen="20",
             seq=seq[4:17], qual="I"*13)
    b = dict(qname="pair1", flag="147", rname=source, pos="12", mapq="1",
             cigar="13M", rnext="=", pnext="5", tlen="-20",
             seq=seq[11:24], qual="H"*13)
    return [a, b]


class ExactPairRemapTests(unittest.TestCase):
    def setUp(self):
        self.refs = {"src": SOURCE, "forward": FORWARD, "reverse": REVERSE}

    def test_unique_forward(self):
        self.assertEqual(unique_placement(FORWARD, TEMPLATE), (4, False))

    def test_unique_reverse(self):
        self.assertEqual(unique_placement(REVERSE, TEMPLATE), (4, True))

    def test_forward_pair_is_exact_and_reuses_qname(self):
        copied = lift_pair(pair(), self.refs, "forward")
        self.assertEqual([r["pos"] for r in copied], ["5", "12"])
        self.assertEqual([r["flag"] for r in copied], ["99", "147"])
        self.assertEqual([r["qname"] for r in copied], ["pair1", "pair1"])
        self.assertTrue(all(r["mapq"] == "0" for r in copied))
        self.assertEqual([r["pnext"] for r in copied], ["12", "5"])
        self.assertEqual([r["tlen"] for r in copied], ["20", "-20"])

    def test_reverse_pair_recomputes_geometry_and_bases(self):
        copied = lift_pair(pair(), self.refs, "reverse")
        self.assertEqual([r["pos"] for r in copied], ["12", "5"])
        self.assertEqual([r["flag"] for r in copied],
                         [str(99 ^ 0x30), str(147 ^ 0x30)])
        self.assertEqual(copied[0]["seq"],
                         reverse_complement(pair()[0]["seq"]))
        self.assertEqual(copied[0]["qual"], "I"*13)
        self.assertEqual([r["pnext"] for r in copied], ["5", "12"])
        self.assertEqual([r["tlen"] for r in copied], ["-20", "20"])

    def test_source_template_repeated_rejected(self):
        refs = dict(self.refs, src=SOURCE + "CC" + TEMPLATE)
        self.assertIsNone(lift_pair(pair(), refs, "forward"))

    def test_target_repeat_rejected(self):
        refs = dict(self.refs, forward=FORWARD + "CC" + TEMPLATE)
        self.assertIsNone(lift_pair(pair(), refs, "forward"))

    def test_target_reverse_repeat_rejected(self):
        refs = dict(self.refs, forward=FORWARD + reverse_complement(TEMPLATE))
        self.assertIsNone(lift_pair(pair(), refs, "forward"))

    def test_phase_snp_in_unsequenced_gap_blocks_transfer(self):
        # Shorter mates leave an unsequenced gap. Its reference must still match.
        reads = pair()
        for r in reads:
            r["cigar"] = "6M"
            r["seq"] = r["seq"][:6]
            r["qual"] = r["qual"][:6]
        mutated = list(FORWARD)
        mutated[13] = "A" if mutated[13] != "A" else "C"
        self.assertIsNone(lift_pair(reads, dict(self.refs,
                                               forward="".join(mutated)),
                                        "forward"))

    def test_no_transfer_of_observed_read_mismatch(self):
        reads = pair()
        reads[0]["seq"] = ("G" if reads[0]["seq"][0] != "G" else "A") + reads[0]["seq"][1:]
        original = [dict(r) for r in reads]
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))
        self.assertEqual(reads, original)  # original variant is retained

    def test_no_transfer_of_second_mate_variant(self):
        reads = pair()
        reads[1]["seq"] = ("G" if reads[1]["seq"][0] != "G" else "A") + reads[1]["seq"][1:]
        self.assertIsNone(lift_pair(reads, self.refs, "reverse"))

    def test_single_read_not_transferred(self):
        self.assertIsNone(lift_pair(pair()[:1], self.refs, "forward"))

    def test_indel_cigar_rejected(self):
        reads = pair()
        reads[0]["cigar"] = "6M1I6M"
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_mate_coordinate_inconsistency_rejected(self):
        reads = pair()
        reads[0]["pnext"] = "999"
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_mate_flag_inconsistency_rejected(self):
        reads = pair()
        reads[0]["flag"] = str(99 ^ 0x20)
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_mate_different_reference_rejected(self):
        reads = pair()
        reads[1]["rname"] = "reverse"
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_secondary_alignment_rejected(self):
        reads = pair()
        reads[0]["flag"] = str(99 | 0x100)
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_ambiguous_n_base_rejected(self):
        refs = dict(self.refs, src=SOURCE[:12]+"N"+SOURCE[13:])
        self.assertIsNone(lift_pair(pair(), refs, "forward"))

    def test_template_span_cap(self):
        self.assertIsNone(lift_pair(pair(), self.refs, "forward", 19))

    def test_no_self_transfer(self):
        self.assertIsNone(lift_pair(pair(), self.refs, "src"))

    def test_extra_qname_record_never_propagates(self):
        rows = pair() + [dict(pair()[0], rname="reverse")]
        copies, stats = compatible_copies(self.refs, rows,
                                          ["src", "forward", "reverse"])
        self.assertEqual(copies, [])
        self.assertEqual(stats["nonunique_qname"], 1)

    def test_eligible_pair_propagates_to_both_strands(self):
        copies, stats = compatible_copies(self.refs, pair(),
                                          ["src", "forward", "reverse"])
        self.assertEqual(len(copies), 4)
        self.assertEqual(stats["transferred_pair"], 2)
        self.assertEqual({r["rname"] for r in copies}, {"forward", "reverse"})

    def test_no_phase_snp_in_target(self):
        mutated = FORWARD[:10] + ("A" if FORWARD[10] != "A" else "C") + FORWARD[11:]
        self.assertIsNone(lift_pair(pair(), dict(self.refs, forward=mutated),
                                    "forward"))

    def test_malformed_quality_rejected(self):
        reads = pair()
        reads[0]["qual"] = "I"
        self.assertIsNone(lift_pair(reads, self.refs, "forward"))

    def test_reverse_lift_preserves_canonical_allele_observations(self):
        import random
        from types import SimpleNamespace
        rng = random.Random(20261102)
        left = "".join(rng.choices("ACGT", k=31))
        allele = "".join(rng.choices("ACGT", k=36))
        right = "".join(rng.choices("ACGT", k=31))
        source = "GGGG" + left + allele + right + "TTTT"
        references = {"src": source, "reverse": reverse_complement(source)}
        start = 4 + 31
        masked = SimpleNamespace(sequence=source[:start] + "x"*36
                                 + source[start+36:], start=start,
                                 end=start+36)
        a = dict(qname="test", flag="99", rname="src", pos="15",
                 mapq="1", cigar="55M", rnext="=", pnext="46",
                 tlen="86", seq=source[14:69], qual="I"*55)
        b = dict(qname="test", flag="147", rname="src", pos="46",
                 mapq="1", cigar="55M", rnext="=", pnext="15",
                 tlen="-86", seq=source[45:100], qual="I"*55)
        # Only exact observed mates may be lifted; no allele is invented.
        lifted = lift_pair([a, b], references, "reverse")
        self.assertIsNotNone(lifted)
        before = pooled_site_calls(masked, references, [a, b])
        after = pooled_site_calls(masked, references, [a, b]+lifted)
        self.assertTrue(before)
        self.assertEqual(before, after)

    def test_source_consensus_identity_verified(self):
        stitched = [{"ref": "HCV-1a", "contig": SOURCE},
                    {"ref": "HCV-1a", "contig": FORWARD}]
        remap = [{"region": "1-HCV-1a", "sequence": SOURCE},
                 {"region": "2-HCV-1a", "sequence": FORWARD}]
        self.assertEqual(verified_source_references(
            stitched, remap, ["1-HCV-1a", "2-HCV-1a"]),
            {"1-HCV-1a": SOURCE, "2-HCV-1a": FORWARD})

    def test_renumbered_micall_sources_match_by_exact_sequence(self):
        stitched = [{"ref":"HCV-1a","contig":FORWARD},
                    {"ref":"HCV-1a","contig":SOURCE},
                    {"ref":"unknown","contig":"GCGCGC"}]
        remap = [{"region":"13-HCV-1a","sequence":SOURCE},
                 {"region":"1-unknown-partial","sequence":"GCGCGC"}]
        self.assertEqual(verified_source_references(
            stitched,remap,["13-HCV-1a","1-unknown-partial"]),
            {"13-HCV-1a":SOURCE,"1-unknown-partial":"GCGCGC"})

    def test_duplicate_identical_stitched_source_fails_closed(self):
        stitched = [{"ref":"HCV-1a","contig":SOURCE}]*2
        remap = [{"region":"13-HCV-1a","sequence":SOURCE}]
        with self.assertRaisesRegex(ValueError,"No unique exact stitched"):
            verified_source_references(stitched,remap,["13-HCV-1a"])

    def test_wrong_reference_label_rejected_despite_equal_sequence(self):
        stitched = [{"ref":"HCV-1a","contig":SOURCE}]
        remap = [{"region":"13-HIV1-B","sequence":SOURCE}]
        with self.assertRaisesRegex(ValueError,"label does not match"):
            verified_source_references(stitched,remap,["13-HIV1-B"])

    def test_changed_remap_consensus_fails_closed(self):
        stitched = [{"ref": "HCV-1a", "contig": SOURCE}]
        remap = [{"region": "1-HCV-1a", "sequence": SOURCE[:-1]+"A"}]
        with self.assertRaises(ValueError):
            verified_source_references(stitched, remap, ["1-HCV-1a"])

    def test_missing_source_reference_fails_closed(self):
        with self.assertRaises(ValueError):
            verified_source_references([], [{"region": "1-HCV-1a",
                                              "sequence": SOURCE}], ["1-HCV-1a"])

    def test_repeated_remap_reference_fails_closed(self):
        with self.assertRaises(ValueError):
            verified_source_references(
                [{"ref": "HCV-1a", "contig": SOURCE}],
                [{"region": "1-HCV-1a", "sequence": SOURCE}]*2,
                ["1-HCV-1a"])

    def test_duplicate_reference_selection_rejected(self):
        with self.assertRaises(ValueError):
            compatible_copies(self.refs, pair(), ["src", "src"])


if __name__ == "__main__":
    unittest.main()
