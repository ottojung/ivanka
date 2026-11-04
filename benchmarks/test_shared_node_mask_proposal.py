"""Synthetic, reference-independent tests for a read-only shared-node proposal."""
import unittest

from shared_node_mask_proposal import proposals

BASES = "ACGT"
LEFT = "C" * 31
RIGHT = "T" * 31
ALLELE = "ACGA"
MASKED = LEFT + "xxxx" + RIGHT
REFERENCE = "G" * 400 + LEFT + ALLELE + RIGHT + "G" * 400


def row(name="2-HCV-1a", sequence=REFERENCE):
    return {"region": name, "sequence": sequence}


def final(region="1-HCV-1a", sequence=MASKED):
    return {"sample": "synthetic", "region": region, "q-cutoff": "15",
            "consensus-percent-cutoff": "MAX", "offset": "400",
            "sequence": sequence}


def signature(number):
    return "".join(BASES[(number // (4**j)) % 4] for j in range(4))


def paired_rows(count=101, duplicate_signatures=False):
    reads = []
    first = REFERENCE[400:500]
    for i in range(count):
        name = f"pair{i}"
        second = "G" * 96 + signature(0 if duplicate_signatures else i)
        for flag, position, mate_position, sequence in (
            (99, 401, 600, first), (147, 600, 401, second)
        ):
            reads.append({
                "qname": name, "flag": str(flag), "rname": "1-HCV-1a",
                "pos": str(position), "rnext": "=", "pnext": str(mate_position),
                "cigar": "100M", "seq": sequence, "qual": "I" * 100,
            })
    return reads


def refs():
    alternative = "G" * 398 + "AA" + REFERENCE[400:]
    return [row("1-HCV-1a"), row("2-HCV-1a", alternative)]


class SharedNodeProposalTests(unittest.TestCase):
    def test_full_observed_local_allele_is_proposed_without_mutating_input(self):
        original = final()
        output, evidence = proposals([original], refs(), paired_rows())
        self.assertEqual(original["sequence"], MASKED)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(output[0]["sequence"], LEFT + ALLELE + RIGHT)
        self.assertEqual(evidence[0]["reference_names"],
                         ["1-HCV-1a", "2-HCV-1a"])
        self.assertEqual(evidence[0]["length"], 4)
        self.assertGreaterEqual(
            evidence[0]["minimum_distinct_pair_sequences_per_base"], 100)
        self.assertEqual(
            evidence[0]["complete_local_allele_distinct_pair_sequences"], 101)
        self.assertTrue(evidence[0]["original_qnames_only"])
        self.assertEqual(evidence[0]["minimum_shared_allele_fraction"], 1)

    def test_insufficient_distinct_reads_or_sequence_signatures_fail_closed(self):
        for reads in (paired_rows(99), paired_rows(101, True)):
            with self.subTest(records=len(reads)):
                output, evidence = proposals([final()], refs(), reads)
                self.assertEqual(evidence, [])
                self.assertEqual(output[0]["sequence"], MASKED)

    def test_competing_allele_can_veto_a_high_depth_proposal(self):
        records = paired_rows(101)
        competing = paired_rows(30)
        for record in competing:
            record["qname"] = "other-" + record["qname"]
            if record["flag"] == "99":
                sequence = record["seq"]
                record["seq"] = sequence[:31] + "T" + sequence[32:]
        output, evidence = proposals([final()], refs(), records + competing)
        self.assertEqual(evidence, [])
        self.assertEqual(output[0]["sequence"], MASKED)
        # Fraction limit is independently selectable for scientific study,
        # but lowering it does not qualify a clinical or physical result.
        exploratory, found = proposals(
            [final()], refs(), records + competing,
            minimum_allele_fraction=0.75)
        self.assertEqual(len(found), 1)
        self.assertLess(found[0]["minimum_shared_allele_fraction"], 0.95)
        self.assertEqual(exploratory[0]["sequence"], LEFT + ALLELE + RIGHT)

    def test_conflicting_reference_alleles_are_not_resolved_by_majority(self):
        other = "G" * 400 + LEFT + "TTGA" + RIGHT + "G" * 400
        output, evidence = proposals([final()],
                                     [row("1-HCV-1a"),
                                      row("2-HCV-1a", other)], paired_rows())
        self.assertEqual(evidence, [])
        self.assertEqual(output[0]["sequence"], MASKED)

    def test_single_reference_and_other_genotype_are_not_pooled(self):
        for names in ([row("1-HCV-1a")],
                      [row("1-HCV-1a"), row("2-HCV-2a")]):
            with self.subTest(refs=[r["region"] for r in names]):
                output, evidence = proposals([final()], names, paired_rows())
                self.assertEqual(evidence, [])
                self.assertEqual(output[0]["sequence"], MASKED)

    def test_synthetic_projection_names_are_forbidden(self):
        reads = paired_rows()
        reads[0]["qname"] += "|ivanka_hypothesis=2-HCV-1a"
        with self.assertRaisesRegex(ValueError, "original remap"):
            proposals([final()], refs(), reads)

    def test_non_max_non_q15_and_non_hcv_records_remain_unchanged(self):
        entries = [dict(final(), **{"q-cutoff": "20"}),
                   dict(final(), **{"consensus-percent-cutoff": "0.100"}),
                   final(region="HLA-B")]
        output, evidence = proposals(entries, refs(), paired_rows())
        self.assertEqual(evidence, [])
        self.assertEqual(output, entries)

    def test_duplicate_references_and_invalid_depth_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            proposals([final()], refs() + [row("1-HCV-1a")], paired_rows())
        with self.assertRaisesRegex(ValueError, "Positive"):
            proposals([final()], refs(), paired_rows(), required_depth=0)
        for invalid in (0, -0.1, 1.1):
            with self.assertRaisesRegex(ValueError, "Minimum allele fraction"):
                proposals([final()], refs(), paired_rows(),
                          minimum_allele_fraction=invalid)


if __name__ == "__main__":
    unittest.main()
