"""Unphased homologous-locus groups never duplicate original paired reads."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from original_pair_homologous_loci import source_bound
from original_pair_locus_groups import locus_groups
from original_pair_locus_evidence import evaluate_loci
from synthetic_phase_pairs import generate


class HomologousOriginalPairLocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.linked = generate(
            cls.root / "linked", variants=(280, 400),
            pairs_per_haplotype=500, seed=17, error_rate=0.002)
        cls.unlinked = generate(
            cls.root / "unlinked", variants=(280, 900),
            pairs_per_haplotype=500, seed=17, error_rate=0.002)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def records(self, truth):
        a,b = truth["phase_coupled_haplotypes"]
        p=truth["variant_positions_zero_based"][-1]
        alt=list(a)
        alt[p]=b[p]
        return [("true A",a),("true B",b),
                ("recombinant","".join(alt))]

    def evaluate(self, case, records=None):
        truth=getattr(self,case)
        folder=self.root / case
        return evaluate_loci(self.records(truth) if records is None else records,
                             folder/"synthetic_R1.fastq.gz",
                             folder/"synthetic_R2.fastq.gz",
                             max_pairs=1000,max_contigs=4)

    def test_200bp_homologous_groups_reveal_recombinant_not_true_truth(self):
        report=self.evaluate("linked")
        self.assertEqual(report["unique_local_variant_groups_screened"],2)
        self.assertEqual(len(report["unique_shared_locus_evidence"]),2)
        rows={row["contig"]:row for row in report["results"]}
        self.assertEqual(rows["true A"]["tentative_conflict_positions"],[])
        self.assertEqual(rows["true B"]["tentative_conflict_positions"],[])
        self.assertEqual(rows["recombinant"]["tentative_conflict_positions"],
                         [[280,400]])
        self.assertFalse(rows["recombinant"]["delete_or_filter_contig"])
        self.assertTrue(report[
            "original_pairs_not_multiplied_across_equivalent_contigs"])
        self.assertFalse(report["full_length_haplotype_phase_inferred"])

    def test_original_qname_support_not_multiplied_by_duplicate_contigs(self):
        base=self.records(self.linked)
        single=self.evaluate("linked",base)
        copy=self.evaluate("linked",base+[("same truth duplicated",base[0][1])])
        self.assertEqual(single["unique_shared_locus_evidence"][0][
            "q15_original_pair_allele_counts"],
            copy["unique_shared_locus_evidence"][0][
            "q15_original_pair_allele_counts"])
        self.assertEqual(single["unique_direct_original_pair_link_evidence"],
                         copy["unique_direct_original_pair_link_evidence"])
        self.assertEqual(
            len(copy["results"][0]["qualifying_locus_sites"]),2)
        self.assertNotIn("q15_original_pair_allele_counts",
                         str(copy["results"]))

    def test_unlinked_control_never_invents_a_bridge(self):
        report=self.evaluate("unlinked")
        self.assertEqual(report["unique_local_variant_groups_screened"],2)
        self.assertFalse(any(row["tentative_conflict_positions"]
                             for row in report["results"]))
        self.assertEqual(report["unique_direct_original_pair_link_evidence"],[])
        self.assertFalse(report["full_length_haplotype_phase_inferred"])

    def test_homopolymer_and_short_context_collisions_fail_closed(self):
        _,_,groups,scope=locus_groups([("low complexity","A"*100)])
        self.assertEqual(len(groups),0)
        self.assertGreater(scope["excluded_ambiguous_or_repeated_groups"],0)
        first="A"*8+"C"*7+"A"+"G"*7+"A"*8
        other="T"*8+"C"*7+"A"+"G"*7+"T"*8
        index,_,groups,_=locus_groups([("a",first),("b",other)])
        self.assertEqual(len(index),0)
        self.assertEqual(len(groups),0)

    def test_source_hash_binding_and_invalid_parameter_guards(self):
        truth=self.linked
        records=self.records(truth)
        fasta=self.root/"source-pinned.fasta"
        fasta.write_text("".join(f">{name}\n{seq}\n" for name,seq in records))
        folder=self.root/"linked"
        r1=folder/"synthetic_R1.fastq.gz"
        r2=folder/"synthetic_R2.fastq.gz"
        hashes=tuple(hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (fasta,r1,r2))
        report=source_bound(fasta,r1,r2,hashes,max_pairs=1000,max_contigs=3,
                            select="original")
        self.assertTrue(report["source_verified_before_and_after"])
        self.assertEqual(report["screening_order"],"original_fasta_order")
        self.assertEqual(report["unique_local_variant_groups_screened"],2)
        with self.assertRaisesRegex(ValueError,"SHA256"):
            source_bound(fasta,r1,r2,("0"*64,*hashes[1:]),max_pairs=1000)
        with self.assertRaises(ValueError):
            self.evaluate("linked",records=[])
        with self.assertRaises(ValueError):
            evaluate_loci(records,r1,r2,max_pairs=True)
        with self.assertRaises(ValueError):
            locus_groups(records,short_flank=15,long_flank=15)


if __name__ == "__main__":
    unittest.main()
