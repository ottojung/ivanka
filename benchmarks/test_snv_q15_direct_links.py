"""Direct original-pair Q15 local linkage, never transitive inference."""
import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from snv_q15_direct_links import direct_links


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DirectOriginalPairSNVLinks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        rng = random.Random(18)
        parent = "".join(rng.choices("ACGT", k=220))
        self.marks = (50, 100, 150)
        self.alts = []
        self.ctx31 = []
        self.fasta = root / "base.fasta"
        self.fasta.write_text(">ivanka_1 len=220\n" + parent + "\n")
        self.audit_file = root / "audit.tsv"
        metadata = [
            "#schema=ivanka.unphased_snv_candidates.v1",
            "#phasing=unidentified; independent_dna_molecules=false",
            "#sampling=first_50000_pairs_every_third_31mer; kmer_counts_are_occurrences_not_molecules; phred_unchecked=true",
            "#ordinary_micall_fasta_unchanged=true",
            "parent_fasta_index\tlength\tsnv_offset_zero_based\tbaseline_base\talternate_base\tassembling_read_record_support\tnovel_sampled_31mers_ge5\tlocal_61base_unphased_context",
        ]
        for pos in self.marks:
            alt = next(b for b in "ACGT" if b != parent[pos])
            context = parent[pos-30:pos] + alt + parent[pos+1:pos+31]
            self.alts.append(alt)
            self.ctx31.append(context[15:46])
            metadata.append(f"1\t220\t{pos}\t{parent[pos]}\t{alt}\t170\t15\t{context}")
        self.audit_file.write_text("\n".join(metadata) + "\n")
        self.r1, self.r2 = root / "R1.fastq", root / "R2.fastq"
        self.write_pairs([(0, 1)] * 12 + [(1, 2)] * 12)

    def write_pairs(self, pairs, *, second_low_quality=False):
        with self.r1.open("w") as f1, self.r2.open("w") as f2:
            for i, (a, b) in enumerate(pairs):
                suffix = "".join("ACGT"[(i >> (2 * k)) & 3] for k in range(4))
                one, two = self.ctx31[a] + suffix, self.ctx31[b] + suffix
                q1, q2 = "I" * len(one), "I" * len(two)
                if second_low_quality:
                    q2 = "/" * len(two)
                for handle, mate, seq, qualities in (
                        (f1, 1, one, q1), (f2, 2, two, q2)):
                    handle.write(f"@p{i}/{mate}\n{seq}\n+\n{qualities}\n")
        self.hashes = {name: sha(path) for name, path in (
            ("audit_tsv", self.audit_file),
            ("ordinary_fasta", self.fasta),
            ("original_r1", self.r1),
            ("original_r2", self.r2))}

    def report(self, **opts):
        args = dict(expected_hashes=self.hashes, min_pairs=10)
        args.update(opts)
        return direct_links(self.audit_file, self.fasta, self.r1, self.r2,
                            **args)

    def test_direct_ab_bc_never_implies_transitive_ac(self):
        result = self.report()
        self.assertEqual(result["original_pairs_scanned"], 24)
        self.assertEqual(result["candidate_pair_count"], 3)
        self.assertTrue(all(v["candidate_meets_local_q15_screen"]
                            for v in result["qualified_unphased_nodes"]))
        edges = {tuple(x["candidate_indices_zero_based"]): x
                 for x in result["direct_allele_link_evidence"]}
        self.assertEqual(edges[0, 1]["observed_joint_original_pair_ids"][
            "alternative_alternative"], 12)
        self.assertEqual(edges[1, 2]["observed_joint_distinct_consistent_pair_sequences"][
            "alternative_alternative"], 12)
        self.assertTrue(edges[0, 1]["direct_local_link_supported"])
        self.assertTrue(edges[1, 2]["direct_local_link_supported"])
        self.assertFalse(edges[0, 2]["direct_local_link_supported"])
        self.assertEqual(edges[0, 2]["observed_joint_original_pair_ids"][
            "alternative_alternative"], 0)
        self.assertFalse(result["transitive_links_created"])
        self.assertFalse(result["full_length_haplotype_phase_inferred"])

    def test_q14_second_mate_vetoes_both_joint_links(self):
        self.write_pairs([(0, 1)] * 12 + [(1, 2)] * 12,
                         second_low_quality=True)
        result = self.report()
        self.assertEqual(sum(x["direct_local_link_supported"]
                             for x in result["direct_allele_link_evidence"]), 0)
        # B retains Q15-only standalone support from the opposite R1 mate,
        # but no two-marker direct pair passes when all second mates are Q14.
        self.assertTrue(result["qualified_unphased_nodes"][1][
            "candidate_meets_local_q15_screen"])

    def test_repeat_identical_pair_sequence_cannot_create_independent_links(self):
        self.write_pairs([(0, 1)] * 12)
        # All read pairs carry the same sequences, but have distinct IDs.
        first = self.r1.read_text().splitlines()
        second = self.r2.read_text().splitlines()
        for records in (first, second):
            for i in range(1, 12):
                records[i*4+1] = records[1]
                records[i*4+3] = records[3]
        self.r1.write_text("\n".join(first) + "\n")
        self.r2.write_text("\n".join(second) + "\n")
        self.hashes["original_r1"] = sha(self.r1)
        self.hashes["original_r2"] = sha(self.r2)
        result = self.report()
        edge = result["direct_allele_link_evidence"][0]
        self.assertEqual(edge["observed_joint_original_pair_ids"][
            "alternative_alternative"], 12)
        self.assertEqual(edge["observed_joint_distinct_consistent_pair_sequences"][
            "alternative_alternative"], 1)
        self.assertFalse(edge["direct_local_link_supported"])

    def test_partially_observed_duplicate_pair_sequence_is_not_a_joint_signature(self):
        self.write_pairs([(0, 1)] * 12)
        r1 = self.r1.read_text().splitlines()
        r2 = self.r2.read_text().splitlines()
        # Pair 1 has exactly the same paired nucleotide sequences as
        # pair 0, but its second mate has Q14, so the signature is partial.
        r1[5] = r1[1]
        r2[5] = r2[1]
        r2[7] = "/" * len(r2[7])
        self.r1.write_text("\n".join(r1) + "\n")
        self.r2.write_text("\n".join(r2) + "\n")
        self.hashes["original_r1"] = sha(self.r1)
        self.hashes["original_r2"] = sha(self.r2)
        result = self.report()
        edge = result["direct_allele_link_evidence"][0]
        self.assertEqual(edge["observed_joint_original_pair_ids"][
            "alternative_alternative"], 11)
        self.assertEqual(edge[
            "observed_joint_distinct_consistent_pair_sequences"][
                "alternative_alternative"], 10)

    def test_baseline_baseline_only_does_not_activate_a_variant_edge(self):
        # Both alt nodes individually pass Q15, but NEVER on a pair
        # together; high reference/reference co-coverage is not an SNV link.
        alt0, alt1 = self.ctx31[:2]
        parent = self.fasta.read_text().splitlines()[1]
        ref0, ref1 = (parent[p-15:p+16] for p in self.marks[:2])
        events = [(alt0, "G"*35)]*12 + [("G"*35, alt1)]*12
        events += [(ref0, ref1)]*12
        with self.r1.open("w") as a, self.r2.open("w") as b:
            for i,(one,two) in enumerate(events):
                suffix = "".join("ACGT"[(i>>(2*j))&3] for j in range(4))
                for out, mate, word in ((a,1,one),(b,2,two)):
                    seq = word+suffix
                    out.write(f"@p{i}/{mate}\n{seq}\n+\n{'I'*len(seq)}\n")
        self.hashes["original_r1"] = sha(self.r1)
        self.hashes["original_r2"] = sha(self.r2)
        result = self.report()
        self.assertTrue(all(x["candidate_meets_local_q15_screen"]
                            for x in result["qualified_unphased_nodes"][:2]))
        edge = result["direct_allele_link_evidence"][0]
        self.assertEqual(edge["observed_joint_original_pair_ids"][
            "reference_reference"], 12)
        self.assertEqual(edge["supported_direct_local_allele_combinations"], [])
        self.assertFalse(edge["direct_local_link_supported"])

    def test_input_tampering_and_unqualified_nodes_withhold_all(self):
        result = self.report(min_pairs=13)
        self.assertFalse(any(x["direct_local_link_supported"]
                             for x in result["direct_allele_link_evidence"]))
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.report(expected_hashes=dict(
                self.hashes, original_r2="0"*64))
        self.audit_file.write_text(
            self.audit_file.read_text().replace(
                "#phasing=unidentified", "#phasing=phased"))
        self.hashes["audit_tsv"] = sha(self.audit_file)
        with self.assertRaisesRegex(ValueError, "unphased"):
            self.report()


if __name__ == "__main__":
    unittest.main()
