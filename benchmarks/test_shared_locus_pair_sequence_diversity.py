"""CPU-only invariants for read-pair sequence diversity at shared loci."""
import random
import unittest
from types import SimpleNamespace

from shared_locus_pair_sequence_diversity import (
    audit, paired_sequence_signature, reverse_complement,
)


def fixture():
    rng = random.Random(10520261102)
    left = "".join(rng.choices("ACGT", k=30)) + "C"
    allele = "A" + "".join(rng.choices("ACGT", k=35))
    right = "".join(rng.choices("ACGT", k=31))
    reference = left + allele + right + "GGGG"
    masked = SimpleNamespace(sequence=left+"x"*36+right+"GGGG",
                             start=31, end=67)
    return reference, masked


def pair(name, reference, target="a"):
    a = dict(qname=name, flag="99", rname=target, pos="1",
             mapq="1", cigar="55M", rnext="=", pnext="44",
             tlen="98", seq=reference[:55], qual="I"*55)
    b = dict(qname=name, flag="147", rname=target, pos="44",
             mapq="1", cigar="55M", rnext="=", pnext="1",
             tlen="-98", seq=reference[43:98], qual="I"*55)
    return [a, b]


def reverse_pair(rows, target="b"):
    a, b = rows
    result = [dict(a, flag=str(99 ^ 0x30), rname=target,
                   pos="44", pnext="1", tlen="-98",
                   seq=reverse_complement(a["seq"]), qual=a["qual"][::-1]),
              dict(b, flag=str(147 ^ 0x30), rname=target,
                   pos="1", pnext="44", tlen="98",
                   seq=reverse_complement(b["seq"]), qual=b["qual"][::-1])]
    return result


class SharedLocusPairSequenceTests(unittest.TestCase):
    def setUp(self):
        self.ref, self.masked = fixture()
        self.refs = {"a": self.ref, "b": self.ref}

    def site(self, rows, i=0, refs=None):
        return audit(self.masked, refs or self.refs, rows)["per_position"][i]

    def test_identical_sequences_two_ids_one_signature(self):
        rows = pair("q1", self.ref) + pair("q2", self.ref)
        result = audit(self.masked, self.refs, rows)
        site = result["per_position"][0]["alleles"]["A"]
        self.assertEqual(site, {"read_pair_ids": 2,
                                "distinct_paired_sequences": 1})
        self.assertEqual(result["distinct_paired_sequences_across_pairs"], 1)

    def test_distinct_observed_alleles_are_preserved(self):
        alternative = pair("q2", self.ref)
        alternative[0]["seq"] = alternative[0]["seq"][:31]+"G"+alternative[0]["seq"][32:]
        site = self.site(pair("q1", self.ref)+alternative)
        self.assertEqual(site["alleles"]["A"]["read_pair_ids"], 1)
        self.assertEqual(site["alleles"]["G"]["read_pair_ids"], 1)
        self.assertEqual(site["alleles"]["G"]["distinct_paired_sequences"], 1)

    def test_reverse_orientation_deduplicates_same_observed_pair(self):
        forward = pair("q1", self.ref)
        reverse = reverse_pair(pair("q2", self.ref))
        self.assertEqual(paired_sequence_signature(forward),
                         paired_sequence_signature(reverse))
        refs = {"a": self.ref, "b": reverse_complement(self.ref)}
        site = self.site(forward+reverse, refs=refs)
        self.assertEqual(site["alleles"]["A"]["read_pair_ids"], 2)
        self.assertEqual(site["alleles"]["A"]["distinct_paired_sequences"], 1)

    def test_conflicting_mates_are_excluded_at_site(self):
        rows = pair("q1", self.ref)
        site_index = 12
        original = rows[1]["seq"][0]
        rows[1]["seq"] = ("A" if original != "A" else "C")+rows[1]["seq"][1:]
        site = self.site(rows, site_index)
        self.assertEqual(site["conflicted_read_pair_ids"], 1)
        self.assertEqual(site["alleles"][self.ref[31+site_index]]["read_pair_ids"], 0)

    def test_low_quality_base_does_not_support_site(self):
        rows = pair("q1", self.ref)
        rows[0]["qual"] = rows[0]["qual"][:31]+"!"+rows[0]["qual"][32:]
        site = self.site(rows)
        self.assertEqual(site["alleles"]["A"]["read_pair_ids"], 0)

    def test_extra_mapping_rejects_entire_qname(self):
        rows = pair("q1", self.ref)
        result = audit(self.masked, self.refs, rows+[dict(rows[0])])
        self.assertEqual(result["eligible_read_pairs"], 0)
        self.assertEqual(result["invalid_or_nonunique_read_pairs"], 1)

    def test_mate_position_mismatch_rejected(self):
        rows = pair("q1", self.ref)
        rows[0]["pnext"] = "90"
        self.assertIsNone(paired_sequence_signature(rows))

    def test_micall_nonstandard_tlen_is_not_a_pair_identity_gate(self):
        rows = pair("q1", self.ref)
        rows[1]["tlen"] = rows[0]["tlen"]
        self.assertIsNotNone(paired_sequence_signature(rows))

    def test_secondary_alignment_rejected(self):
        rows = pair("q1", self.ref)
        rows[0]["flag"] = str(99 | 0x100)
        self.assertIsNone(paired_sequence_signature(rows))

    def test_wrong_orientation_rejected(self):
        rows = pair("q1", self.ref)
        rows[0]["flag"] = str(99 ^ 0x10)
        self.assertIsNone(paired_sequence_signature(rows))

    def test_ambiguous_signature_with_different_locus_alleles_is_excluded(self):
        first = pair("q1", self.ref)
        shifted = pair("q2", self.ref)
        for row in shifted:
            row["pos"] = str(int(row["pos"])+1)
            row["pnext"] = str(int(row["pnext"])+1)
        self.assertEqual(paired_sequence_signature(first),
                         paired_sequence_signature(shifted))
        site = self.site(first+shifted)
        self.assertEqual(site["alleles"]["A"]["read_pair_ids"], 1)
        self.assertEqual(site["alleles"]["C"]["read_pair_ids"], 1)
        self.assertEqual(site["alleles"]["A"]["distinct_paired_sequences"], 0)
        self.assertEqual(site["ambiguous_paired_sequences"], 1)

    def test_malformed_cigar_pair_fails_closed(self):
        rows = pair("q1", self.ref)
        rows[0]["cigar"] = "BAD"
        result = audit(self.masked, self.refs, rows)
        self.assertEqual(result["eligible_read_pairs"], 0)
        self.assertEqual(result["invalid_or_nonunique_read_pairs"], 1)

    def test_no_observations_returns_zero_without_claim(self):
        result = audit(self.masked, self.refs, [])
        self.assertEqual(result["minimum_seed_read_pair_ids"], 0)
        self.assertEqual(result["minimum_seed_distinct_paired_sequences"], 0)

    def test_non_acgt_read_rejected(self):
        rows = pair("q1", self.ref)
        rows[0]["seq"] = "N"+rows[0]["seq"][1:]
        self.assertIsNone(paired_sequence_signature(rows))


if __name__ == "__main__":
    unittest.main()
