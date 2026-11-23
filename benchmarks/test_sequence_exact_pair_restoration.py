"""Exact-reference replay must preserve original mate identity and multiplicity."""
import unittest
from sequence_exact_pair_restoration import (project_original_pairs,
    original_pairs,valid_baseline_alignment)
from snv_q15_evidence import reverse_complement


def pair(name, ref, seq='ACGTACTT', qual='I'*8, pos=2, flags=(99,147)):
    rows=[]
    for i,flag in enumerate(flags):
        rows.append(dict(qname=name,flag=str(flag),rname=ref,pos=str(pos),
                         mapq='20',cigar='8M',rnext='=',pnext=str(pos),
                         tlen='8',seq=seq,qual=qual))
    return rows


class ExactPairRestorationTests(unittest.TestCase):
    def setUp(self):
        self.reference='AACGTACTTCCGCTAG'
        self.baseref={'1-HCV-1a':self.reference}
        self.candidateref={'8-HCV-1a':self.reference,
                           '9-HCV-1a':'AACGTACTTCCACTAG'}
        self.baseline=pair('readA','1-HCV-1a')
        self.candidate=pair('readA','9-HCV-1a')

    def run_projection(self,**opts):
        return project_original_pairs(
            opts.get('baseline',self.baseline),self.baseref,
            opts.get('candidate',self.candidate),
            opts.get('references',self.candidateref))

    def test_restores_exact_reference_under_different_name_without_extra_reads(self):
        output,stats=self.run_projection()
        self.assertEqual(stats['restored_original_pairs'],1)
        self.assertEqual(len(output),2)
        self.assertEqual({r['rname'] for r in output},{'8-HCV-1a'})
        self.assertEqual(set(original_pairs(output)),{'readA'})
        self.assertEqual({r['seq'] for r in output},{'ACGTACTT'})

    def test_reverse_strand_orientation_can_replay_original_mate(self):
        baseline=pair('readA','1-HCV-1a',flags=(83,163))
        candidate=pair('readA','9-HCV-1a',
                       seq=reverse_complement('ACGTACTT'),flags=(99,147))
        projected,stats=self.run_projection(baseline=baseline,candidate=candidate)
        self.assertEqual(stats['restored_original_pairs'],1)
        self.assertEqual(stats['reverse_oriented_pairs_restored'],1)
        self.assertEqual([r['flag'] for r in projected],['83','163'])
        self.assertEqual([r['seq'] for r in projected],['ACGTACTT']*2)

    def test_gapped_cigar_is_accepted_only_with_correct_reference_span(self):
        cigar=pair('x','old')[0]
        cigar['cigar']='4M1D4M'
        self.assertTrue(valid_baseline_alignment(cigar,self.reference))
        cigar['cigar']='4M1I3M'
        self.assertTrue(valid_baseline_alignment(cigar,self.reference))
        cigar['cigar']='2S4M1D2M'
        self.assertTrue(valid_baseline_alignment(cigar,self.reference))
        for invalid in ('4M1P4M','3M1S4M','4M1D4M1S','4M1D999M'):
            cigar['cigar']=invalid
            self.assertFalse(valid_baseline_alignment(cigar,self.reference))

    def test_missing_or_ambiguous_identical_reference_withheld(self):
        for refs in ({'other':'G'*16},dict(self.candidateref,duplicate=self.reference)):
            with self.subTest(refs=refs):
                output,stats=self.run_projection(references=refs)
                self.assertEqual(stats['restored_original_pairs'] if 'restored_original_pairs' in stats else 0,0)
                self.assertEqual(output,self.candidate)

    def test_modified_read_bytes_or_invalid_alignment_withheld(self):
        different=pair('readA','9-HCV-1a',seq='GGGGGGGG')
        out,stats=self.run_projection(candidate=different)
        self.assertEqual(out,different)
        self.assertEqual(stats['different_original_mate_bytes'],1)
        wrong=pair('readA','1-HCV-1a',pos=999)
        out,stats=self.run_projection(baseline=wrong)
        self.assertEqual(out,self.candidate)
        self.assertEqual(stats['unsupported_baseline_alignment'],1)

    def test_improper_original_pairs_may_recover_only_with_exact_mate_evidence(self):
        baseline=pair('readA','1-HCV-1a',pos=2)
        candidate=pair('readA','8-HCV-1a',pos=2,flags=(97,145))
        result,stats=project_original_pairs(
            baseline,self.baseref,candidate,self.candidateref,
            restore_improper_pairs=True)
        self.assertEqual([row['flag'] for row in result],['99','147'])
        self.assertEqual(stats['improper_original_pairs_restored'],1)
        self.assertEqual([r['rname'] for r in result],['8-HCV-1a']*2)
        self.assertEqual(len(result),len(candidate))
        unchanged,stats=project_original_pairs(
            baseline,self.baseref,candidate,self.candidateref)
        self.assertEqual(unchanged,candidate)
        self.assertNotIn('improper_original_pairs_restored',stats)

    def test_improper_replay_rejects_mismatched_and_unrelated_originals(self):
        baseline=pair('readA','1-HCV-1a',pos=2)
        candidate=pair('readA','8-HCV-1a',seq='GGGGGGGG',flags=(65,129))
        output,stats=project_original_pairs(
            baseline,self.baseref,candidate,self.candidateref,
            restore_improper_pairs=True)
        self.assertEqual(output,candidate)
        self.assertEqual(stats['improper_pair_mate_bytes_changed'],1)
        extra=pair('other','8-HCV-1a',flags=(65,129))
        output,stats=project_original_pairs(
            baseline,self.baseref,candidate+extra,self.candidateref,
            restore_improper_pairs=True)
        self.assertEqual(len(output),4)
        self.assertEqual([r['qname'] for r in output],[r['qname'] for r in candidate+extra])

    def test_improper_replay_rejects_ambiguous_reference(self):
        baseline=pair('readA','1-HCV-1a',pos=2)
        candidate=pair('readA','8-HCV-1a',pos=2,flags=(97,145))
        refs=dict(self.candidateref,duplicated_exact=self.reference)
        output,stats=project_original_pairs(
            baseline,self.baseref,candidate,refs,
            restore_improper_pairs=True)
        self.assertEqual(output,candidate)
        self.assertEqual(stats['improper_pair_without_unique_exact_reference'],1)

    def test_opt_in_same_reference_alignment_drift_restores_only_verified_mates(self):
        before=pair('readA','1-HCV-1a',pos=2)
        current=pair('readA','8-HCV-1a',pos=4)
        kept,baseline_stats=self.run_projection(baseline=before,candidate=current)
        self.assertEqual(kept,current)
        self.assertNotIn('restored_original_pairs',baseline_stats)
        changed,stats=project_original_pairs(
            before,self.baseref,current,self.candidateref,
            restore_same_reference_drift=True)
        self.assertEqual([r['pos'] for r in changed],['2','2'])
        self.assertEqual(stats['same_reference_alignment_drift_restored'],1)
        self.assertEqual(stats['restored_original_pairs'],1)
        self.assertEqual(len(changed),len(current))
        self.assertEqual({r['rname'] for r in changed},{'8-HCV-1a'})

    def test_opt_in_same_reference_unchanged_placement_noop(self):
        before=pair('readA','1-HCV-1a',pos=2)
        current=pair('readA','8-HCV-1a',pos=2)
        changed,stats=project_original_pairs(
            before,self.baseref,current,self.candidateref,
            restore_same_reference_drift=True)
        self.assertEqual(changed,current)
        self.assertNotIn('restored_original_pairs',stats)

    def test_duplicate_qname_not_counted_or_transplanted(self):
        copied=self.candidate+self.candidate
        output,stats=self.run_projection(candidate=copied)
        self.assertEqual(output,copied)
        self.assertNotIn('readA',original_pairs(output))
        self.assertEqual(stats.get('restored_original_pairs',0),0)

    def test_mapq_is_not_inflated_and_mate_multiplicity_is_constant(self):
        baseline=pair('readA','1-HCV-1a')
        baseline[0]['mapq']='60'
        candidate=pair('readA','9-HCV-1a')
        candidate[0]['mapq']='3'
        output,stats=self.run_projection(baseline=baseline,candidate=candidate)
        self.assertEqual(stats['restored_original_pairs'],1)
        self.assertEqual(output[0]['mapq'],'3')
        self.assertEqual(output[1]['mapq'],'20')
        self.assertEqual(sorted((r['qname'],r['seq']) for r in output),
                         sorted((r['qname'],r['seq']) for r in candidate))


if __name__=='__main__':
    unittest.main()
