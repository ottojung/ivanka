"""Negative A/B release gate, never a positive phase-safety certificate."""
import tempfile
import unittest
from pathlib import Path

from screen_micall_ab_regressions import assess
from test_snv_remap_assignment_ab import make
from test_snv_micall_ab_diagnostics import write_csv


class MiCallRegressionScreenTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.b=root/"baseline"
        self.c=root/"candidate"
        make(self.b,{"q1":"ref-a","q2":"ref-a"})
        make(self.c,{"q1":"ref-a","q2":"ref-a"})
        fields=("region","q-cutoff","consensus-percent-cutoff",
                "offset","sequence")
        nuc=("seed","region","q-cutoff","refseq.nuc.pos","genome.pos",
             "A","C","G","T","coverage")
        row={"region":"HCV","q-cutoff":"15",
             "consensus-percent-cutoff":"MAX","offset":"0",
             "sequence":"ACGT"}
        self.original={"seed":"HCV-1a","region":"HCV","q-cutoff":"15",
                      "refseq.nuc.pos":"123","genome.pos":"987",
                      "A":"100","C":"12","G":"0","T":"0","coverage":"112"}
        for folder in (self.b,self.c):
            write_csv(folder/"conseq.csv",fields,[row])
            write_csv(folder/"nuc.csv",nuc,[self.original])

    def test_equal_original_evidence_still_never_proves_safety(self):
        report=assess(self.b,self.c)
        self.assertEqual(report["conservative_observed_regressions"],{})
        self.assertFalse(report["automatic_reconstruction_release_permitted"])
        self.assertFalse(report["full_length_haplotype_phase_verified"])

    def test_minority_allele_loss_is_negative_evidence(self):
        fields=tuple(self.original)
        changed=dict(self.original,C="9",coverage="109")
        write_csv(self.c/"nuc.csv",fields,[changed])
        report=assess(self.b,self.c)
        self.assertEqual(report["conservative_observed_regressions"][
            "lost_q15_alleles_ge_10"],1)

    def test_original_pair_reassignment_requires_review_even_if_q15_unchanged(self):
        make(self.c,{"q1":"ref-b","q2":"ref-a"})
        report=assess(self.b,self.c)
        self.assertEqual(report["conservative_observed_regressions"][
            "original_read_pairs_reassigned_between_contigs"],1)

    def test_unchanged_dna_but_changed_contig_labels_still_blocks_release(self):
        fields=('region','q-cutoff','consensus-percent-cutoff','offset','sequence')
        write_csv(self.c/'conseq.csv',fields,[{
            'region':'renamed-HCV','q-cutoff':'15',
            'consensus-percent-cutoff':'MAX','offset':'2',
            'sequence':'ACGT'}])
        report=assess(self.b,self.c)
        self.assertTrue(report[
            'identical_final_max_nucleotides_ignoring_region_offset'])
        self.assertTrue(report[
            'max_region_offset_changes_still_require_review'])
        self.assertEqual(report['conservative_observed_regressions'][
            'baseline_q15_max_sequences_changed'],1)
        self.assertFalse(report['automatic_reconstruction_release_permitted'])

    def test_readonly_screen_does_not_make_an_unphased_call(self):
        report=assess(self.b,self.c)
        self.assertFalse(report["independent_physical_molecule_counts_verified"])
        self.assertFalse(report["raw_fastq_mate_provenance_verified_by_this_screen"])


if __name__=="__main__":
    unittest.main()
