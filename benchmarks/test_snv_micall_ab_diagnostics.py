"""Read-only alignment comparison does not confuse unmatched with lost depth."""
import csv
import tempfile
import unittest
from pathlib import Path
from snv_micall_ab_diagnostics import compare


def write_csv(path,columns,rows):
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class SNVFullMicallABTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.base=root/"baseline"
        self.candidate=root/"candidate"
        self.base.mkdir()
        self.candidate.mkdir()
        self.conseq_fields=("region","q-cutoff","consensus-percent-cutoff",
                            "offset","sequence")
        self.nuc_fields=("seed","region","q-cutoff","refseq.nuc.pos",
                         "genome.pos","A","C","G","T","coverage")
        self.conseq={"region":"HCV1","q-cutoff":"15",
                     "consensus-percent-cutoff":"MAX","offset":"0",
                     "sequence":"ACG"}
        self.loci=[
            {"seed":"seed-a","region":"HCV1","q-cutoff":"15",
             "refseq.nuc.pos":str(pos),"genome.pos":str(pos),
             "A":str(a),"C":"8","G":"0","T":"0","coverage":str(a+8)}
            for pos,a in ((10,120),(11,105))]
        self.write(self.base,[self.conseq],self.loci)
        self.write(self.candidate,[self.conseq],self.loci)

    def write(self,folder,conseq,nuc):
        write_csv(folder/"conseq.csv",self.conseq_fields,conseq)
        write_csv(folder/"nuc.csv",self.nuc_fields,nuc)

    def test_unchanged_outputs_do_not_fabricate_changes(self):
        x=compare(self.base,self.candidate)
        self.assertTrue(x["identical_q15_max_sequence_multiset"])
        self.assertTrue(x["no_detected_matched_q15_allele_or_high_depth_loss"])
        self.assertEqual(x["matched_loci_dropped_below_depth_100"],0)
        self.assertEqual(x["baseline_q15_allele_calls_ge_10_lost_on_matched_loci"],0)
        self.assertFalse(x["full_length_haplotype_phase_authenticated"])
        self.assertFalse(x["independent_physical_molecule_count_authenticated"])

    def test_low_depth_and_minor_allele_losses_really_reported(self):
        after=[dict(row) for row in self.loci]
        after[0].update(A="80",C="0",coverage="80")
        self.write(self.candidate,[dict(self.conseq,sequence="ATG")],after)
        x=compare(self.base,self.candidate)
        self.assertFalse(x["identical_q15_max_sequence_multiset"])
        self.assertEqual(x["matched_loci_dropped_below_depth_100"],1)
        self.assertEqual(x["baseline_q15_allele_calls_ge_10_lost_on_matched_loci"],0)
        self.assertEqual(x["baseline_max_sequence_rows_lost"],1)

    def test_missing_locus_not_misreported_as_matched_depth_loss(self):
        self.write(self.candidate,[self.conseq],self.loci[:1])
        x=compare(self.base,self.candidate)
        self.assertEqual(x["baseline_only_q15_nuc_loci"],1)
        self.assertEqual(x["matched_loci_dropped_below_depth_100"],0)
        self.assertEqual(x["baseline_high_depth_loci_missing_candidate"],1)

    def test_label_and_offset_only_changes_preserve_nucleotide_multiset(self):
        modified=dict(self.conseq,region='renamed',offset='5')
        self.write(self.candidate,[modified],self.loci)
        report=compare(self.base,self.candidate)
        self.assertFalse(report['identical_q15_max_sequence_multiset'])
        self.assertTrue(report[
            'identical_q15_max_nucleotide_multiset_ignoring_region_offset'])
        self.assertEqual(report[
            'baseline_max_nucleotide_sequences_lost_ignoring_region_offset'],0)
        self.assertEqual(report[
            'candidate_max_nucleotide_sequences_added_ignoring_region_offset'],0)
        self.assertTrue(report[
            'max_region_or_offset_associations_differ_but_nucleotides_equal'])
        self.assertTrue(report[
            'same_nucleotide_sequences_do_not_prove_placement_or_phase'])
        self.assertEqual(report['baseline_max_sequence_rows_lost'],1)

    def test_real_max_sequence_change_does_not_look_like_a_rename(self):
        modified=dict(self.conseq,region='renamed',offset='5',sequence='ATG')
        self.write(self.candidate,[modified],self.loci)
        report=compare(self.base,self.candidate)
        self.assertFalse(report[
            'identical_q15_max_nucleotide_multiset_ignoring_region_offset'])
        self.assertEqual(report[
            'baseline_max_nucleotide_sequences_lost_ignoring_region_offset'],1)
        self.assertEqual(report[
            'candidate_max_nucleotide_sequences_added_ignoring_region_offset'],1)
        self.assertFalse(report[
            'max_region_or_offset_associations_differ_but_nucleotides_equal'])

    def test_multiset_counts_cannot_be_reduced_to_set_membership(self):
        before=[self.conseq,dict(self.conseq,region='duplicate')]
        self.write(self.base,before,self.loci)
        self.write(self.candidate,[self.conseq],self.loci)
        report=compare(self.base,self.candidate)
        self.assertFalse(report[
            'identical_q15_max_nucleotide_multiset_ignoring_region_offset'])
        self.assertEqual(report[
            'baseline_max_nucleotide_sequences_lost_ignoring_region_offset'],1)

    def test_bool_depth_threshold_and_empty_q15_file_rejected(self):
        for bad in (True, 0, -1):
            with self.assertRaisesRegex(ValueError, "Positive integer"):
                compare(self.base,self.candidate,threshold=bad)
            with self.assertRaisesRegex(ValueError, "Positive integer"):
                compare(self.base,self.candidate,allele_floor=bad)
        self.write(self.candidate,[self.conseq],[])
        with self.assertRaisesRegex(ValueError, "Q15 nucleotide"):
            compare(self.base,self.candidate)

    def test_matching_q15_allele_loss_detected(self):
        after=[dict(row) for row in self.loci]
        after[0].update(A="120",C="0",coverage="120")
        before=[dict(row) for row in self.loci]
        before[0].update(A="120",C="15",coverage="135")
        self.write(self.base,[self.conseq],before)
        self.write(self.candidate,[self.conseq],after)
        x=compare(self.base,self.candidate)
        self.assertEqual(x["baseline_q15_allele_calls_ge_10_lost_on_matched_loci"],1)
        self.assertFalse(x["no_detected_matched_q15_allele_or_high_depth_loss"])


if __name__=="__main__":
    unittest.main()
