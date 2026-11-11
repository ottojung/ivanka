"""Synthetic known truth is evaluated by blinded original FASTQ linkage."""
import tempfile
import random
import unittest
from pathlib import Path

from snv_q15_fastq import iter_original_pairs
from source_q15_phase_bridges import (
    direct_source_links, directly_observed_candidate,
    local_words)
from synthetic_phase_pairs import generate, reverse_complement


class BlindedSourcePhaseTests(unittest.TestCase):
    def generate(self,sites,seed=17,errors=.002):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory=Path(tmp.name)
        truth=generate(directory,variants=sites,seed=seed,error_rate=errors)
        reads=iter_original_pairs(
            directory/'synthetic_R1.fastq.gz',
            directory/'synthetic_R2.fastq.gz',max_pairs=1100)
        return truth,reads

    def test_six_seed_linked_truth_survives_without_phase_oracle(self):
        sites=(280,480)
        for seed in (4,17,18,19,20,39):
            with self.subTest(seed=seed):
                truth,reads=self.generate(sites,seed)
                result=direct_source_links(
                    truth['phase_coupled_haplotypes'][0],sites,reads)
                self.assertGreater(result['original_pairs_with_both_loci_observed'],15)
                self.assertLessEqual(
                    result['original_pairs_with_both_loci_observed'],
                    truth['read_pairs_directly_observing_both_variants'])
                for haplotype in truth['phase_coupled_haplotypes']:
                    candidate=[haplotype[pos] for pos in sites]
                    self.assertEqual(directly_observed_candidate(candidate,result)[
                        'status'],'directly_observed_local_link')
                recombinant=truth['phase_decoupled_haplotypes'][0]
                candidate=[recombinant[pos] for pos in sites]
                self.assertEqual(directly_observed_candidate(candidate,result)[
                    'status'],'unknown')
                self.assertFalse(result['source_haplotype_phase_known'])
                self.assertFalse(result['full_length_phase_or_molecule_independence_proven'])

    def test_base_level_bridge_need_not_supply_full_context(self):
        sites=(280,400)
        truth,reads=self.generate(sites,errors=0)
        self.assertGreater(truth['read_pairs_directly_observing_both_variants'],0)
        report=direct_source_links(truth['phase_coupled_haplotypes'][0],sites,reads)
        self.assertEqual(report['original_pairs_with_both_loci_observed'],0)
        self.assertEqual(report['original_pair_direct_link_counts'],{})

    def test_unlinked_reads_must_not_create_long_range_phase(self):
        sites=(280,900)
        truth,reads=self.generate(sites)
        result=direct_source_links(truth['phase_coupled_haplotypes'][0],sites,reads)
        self.assertEqual(result['original_pairs_with_both_loci_observed'],0)
        self.assertFalse(result['original_pair_direct_link_counts'])
        for haplotype in truth['phase_coupled_haplotypes']:
            self.assertEqual(directly_observed_candidate(
                [haplotype[pos]for pos in sites],result)['status'],'unknown')

    def test_repeated_dna_paired_sequences_do_not_count_as_independent_links(self):
        rng=random.Random(1393)
        template=''.join(rng.choices('ACGT',k=400))
        sites=(80,260)
        words=[local_words(template,pos) for pos in sites]
        seq1=words[0][template[sites[0]]]
        seq2=words[1][template[sites[1]]]
        records=[(f'pair{i}',(seq1,'I'*31),(reverse_complement(seq2),'I'*31))
                 for i in range(12)]
        result=direct_source_links(template,sites,records)
        self.assertEqual(result['original_pairs_scanned'],12)
        self.assertEqual(sum(result['original_pair_direct_link_counts'].values()),12)
        self.assertEqual(sum(result[
            'distinct_consistent_paired_sequence_link_counts'].values()),1)
        self.assertEqual(directly_observed_candidate(
            (template[sites[0]],template[sites[1]]),result)['status'],
            'unknown')

    def test_partial_duplicate_signature_vetoes_distinct_link(self):
        rng=random.Random(1393)
        template=''.join(rng.choices('ACGT',k=400))
        sites=(80,260)
        words=[local_words(template,pos) for pos in sites]
        r1=words[0][template[sites[0]]]
        r2=words[1][template[sites[1]]]
        # Same mate sequences, one copy of locus 2 below Q15.
        records=[('one',(r1,'I'*31),(r2,'I'*31)),
                 ('two',(r1,'I'*31),(r2,'!'*31))]
        result=direct_source_links(template,sites,records)
        self.assertEqual(result['original_pairs_with_both_loci_observed'],1)
        self.assertEqual(sum(result[
            'distinct_consistent_paired_sequence_link_counts'].values()),0)
        self.assertEqual(result['incomplete_paired_sequence_signatures_vetoed'],1)

    def test_one_erroneous_recombinant_signature_cannot_qualify_phase(self):
        # Sequencing errors still occur even when FASTQ qualities say Q40;
        # a single observed false link must never authorize a contig.
        sites=(280,480)
        truth,reads=self.generate(sites,errors=.002)
        evidence=direct_source_links(
            truth['phase_coupled_haplotypes'][0],sites,reads)
        wrong=truth['phase_decoupled_haplotypes'][0]
        call=[wrong[pos] for pos in sites]
        self.assertEqual(directly_observed_candidate(call,evidence)['status'],
                         'unknown')

    def test_both_full_contexts_must_pass_q15(self):
        rng=random.Random(1393)
        template=''.join(rng.choices('ACGT',k=400))
        sites=(80,260)
        words=[local_words(template,pos) for pos in sites]
        x=words[0][template[sites[0]]]
        y=words[1][template[sites[1]]]
        high=('first',(x,'I'*31),(y,'I'*31))
        low=('second',(x,'I'*31),(y,'!'*31))
        observed=direct_source_links(template,sites,[high,low])
        self.assertEqual(observed['original_pairs_with_both_loci_observed'],1)
        self.assertEqual(sum(observed['original_pair_direct_link_counts'].values()),1)

    def test_ambiguous_or_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            direct_source_links('A'*300,(80,80),[])
        with self.assertRaises(ValueError):
            local_words('N'*100,50)
        with self.assertRaisesRegex(ValueError,'Repeated or nonlocal'):
            direct_source_links('A'*200,(50,100),[])
        rng=random.Random(739)
        template=''.join(rng.choices('ACGT',k=400))
        repeated=[('duplicate',('A','I'),('C','I')),
                  ('duplicate',('A','I'),('C','I'))]
        with self.assertRaisesRegex(ValueError,'identifiers must be unique'):
            direct_source_links(template,(80,260),repeated)
        with self.assertRaises(ValueError):
            directly_observed_candidate(('A','N'),{})


if __name__=='__main__':
    unittest.main()
