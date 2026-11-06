"""Original paired reads, not generating haplotype labels, veto false phase."""
import gzip
import tempfile
import unittest
from pathlib import Path

from read_backed_pair_phase import audit_pairwise_phase
from synthetic_phase_pairs import generate
from snv_q15_fastq import iter_original_pairs
from source_q15_phase_bridges import (
    local_words, allele_at_pair)


class OriginalPairPhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def experiment(self, linked=True, pair_count=500):
        sites = (400, 600) if linked else (280, 900)
        truth = generate(self.root / "reads", length=1400,
                         variants=sites, pairs_per_haplotype=pair_count,
                         seed=17)
        r1 = self.root / "reads/synthetic_R1.fastq.gz"
        r2 = self.root / "reads/synthetic_R2.fastq.gz"
        return truth, r1, r2

    def test_bridging_reads_reject_mixed_haplotype_without_truth_labels(self):
        truth, r1, r2 = self.experiment()
        ref = truth["phase_coupled_haplotypes"][0]
        recombinant = truth["phase_decoupled_haplotypes"][0]
        result = audit_pairwise_phase(
            r1, r2, ref, (400, 600), [("unsupported", recombinant)])
        self.assertGreater(result["original_pair_ids_sequencing_both_sites"], 0)
        expected = {tuple(h[p] for p in (400, 600))
                    for h in truth["phase_coupled_haplotypes"]}
        self.assertEqual({tuple(e["allele_pair"])
                          for e in result["phase_observations"]},
                         expected)
        self.assertEqual(result["contigs"][0]["classification"],
                         "unsupported_by_observed_direct_pair_phase")
        self.assertEqual(result["contigs"][0]["supporting_original_pair_ids"], 0)
        self.assertFalse(result["independent_physical_molecules_inferred"])

    def test_true_haplotype_has_direct_pair_support(self):
        truth, r1, r2 = self.experiment()
        ref = truth["phase_coupled_haplotypes"][0]
        result = audit_pairwise_phase(
            r1, r2, ref, (400, 600), [("truth", ref)])
        self.assertEqual(result["contigs"][0]["classification"],
                         "observed_direct_pair_phase")
        self.assertGreater(result["contigs"][0]["supporting_original_pair_ids"], 0)

    def test_no_bridge_yields_unidentifiable_not_false_veto(self):
        truth, r1, r2 = self.experiment(linked=False)
        ref = truth["phase_coupled_haplotypes"][0]
        wrong = truth["phase_decoupled_haplotypes"][0]
        result = audit_pairwise_phase(
            r1, r2, ref, (280, 900), [("unresolved", wrong)])
        self.assertEqual(result["original_pair_ids_sequencing_both_sites"], 0)
        self.assertEqual(result["contigs"][0]["classification"],
                         "not_identifiable_from_direct_pairs")

    def test_low_quality_bases_are_not_direct_phase_evidence(self):
        truth, r1, r2 = self.experiment(pair_count=30)
        for file in (r1, r2):
            with gzip.open(file, "rt") as f:
                lines = f.read().splitlines()
            for i in range(3, len(lines), 4):
                lines[i] = "!" * len(lines[i])
            with gzip.open(file, "wt") as f:
                f.write("\n".join(lines) + "\n")
        ref = truth["phase_coupled_haplotypes"][0]
        result = audit_pairwise_phase(r1, r2, ref, (400, 600),
                                     [("candidate", ref)], minimum_quality=15)
        self.assertEqual(result["original_pair_ids_sequencing_both_sites"], 0)

    def test_wrong_mate_identity_rejected(self):
        truth, r1, r2 = self.experiment(pair_count=2)
        with gzip.open(r2, "rt") as f:
            data = f.read()
        with gzip.open(r2, "wt") as f:
            f.write(data.replace("synthetic:17:0000000", "mismatched", 1))
        with self.assertRaisesRegex(ValueError, "identifiers disagree"):
            audit_pairwise_phase(r1, r2, truth["phase_coupled_haplotypes"][0],
                                 (400, 600), [])

    def test_duplicate_mate_identity_rejected(self):
        truth, r1, r2 = self.experiment(pair_count=2)
        for file in (r1, r2):
            with gzip.open(file, "rt") as f:
                data = f.read()
            with gzip.open(file, "wt") as f:
                f.write(data.replace("synthetic:17:0000002",
                                     "synthetic:17:0000000", 1))
        with self.assertRaisesRegex(ValueError, "Duplicate original"):
            audit_pairwise_phase(r1, r2, truth["phase_coupled_haplotypes"][0],
                                 (400, 600), [])

    def test_single_erroneous_read_pair_cannot_certify_phase(self):
        # Deterministic sequencing errors manufacture one apparent CG
        # original pair, although only CT and GA generate this source.
        sites=(280,480)
        truth=generate(self.root/'erroneous',variants=sites,seed=17,
                       pairs_per_haplotype=1000,error_rate=.002)
        template=truth['phase_coupled_haplotypes'][0]
        wrong=list(template)
        wrong[sites[0]], wrong[sites[1]] = 'C', 'G'
        wrong=''.join(wrong)
        result=audit_pairwise_phase(
            self.root/'erroneous/synthetic_R1.fastq.gz',
            self.root/'erroneous/synthetic_R2.fastq.gz',
            template,sites,[('spurious-CG',wrong),('true',template)],
            anchor=15)
        rows={x['contig']:x for x in result['contigs']}
        self.assertEqual(rows['spurious-CG']['supporting_original_pair_ids'],1)
        self.assertEqual(rows['spurious-CG'][
            'supporting_distinct_consistent_read_pair_sequences'],1)
        self.assertEqual(rows['spurious-CG']['classification'],
                         'weak_direct_pair_phase_observation')
        self.assertEqual(rows['true']['classification'],
                         'observed_direct_pair_phase')
        self.assertFalse(rows['spurious-CG'][
            'may_delete_contig_based_on_this_classification'])
        self.assertTrue(result[
            'absence_of_direct_support_never_proves_biological_absence'])

    def test_many_duplicate_pair_ids_do_not_make_independent_support(self):
        sites=(280,480)
        truth=generate(self.root/'normal',variants=sites,seed=17,
                       pairs_per_haplotype=500,error_rate=0)
        template=truth['phase_coupled_haplotypes'][0]
        src=self.root/'normal'
        words=[local_words(template,site) for site in sites]
        suitable=None
        for qname,a,b in iter_original_pairs(
                src/'synthetic_R1.fastq.gz',
                src/'synthetic_R2.fastq.gz',max_pairs=1100):
            if all(allele_at_pair(a,b,w,15)==template[pos]
                   for pos,w in zip(sites,words)):
                suitable=(a,b)
                break
        self.assertIsNotNone(suitable)
        repeat=self.root/'repeated'
        repeat.mkdir()
        for mate,source in enumerate(suitable,1):
            with gzip.open(repeat/f'R{mate}.fq.gz','wt') as stream:
                for i in range(8):
                    seq,quality=source
                    stream.write(
                        f'@rep{i} {mate}:N:0:0\n{seq}\n+\n{quality}\n')
        args=(repeat/'R1.fq.gz',repeat/'R2.fq.gz',
              template,sites,[('truth',template)])
        result=audit_pairwise_phase(*args,anchor=15)
        row=result['contigs'][0]
        self.assertEqual(row['supporting_original_pair_ids'],8)
        self.assertEqual(row['supporting_distinct_consistent_read_pair_sequences'],1)
        self.assertEqual(row['classification'],
                         'not_identifiable_from_direct_pairs')
        self.assertEqual(result['qualified_direct_pair_allele_combinations'],[])
        explicit=audit_pairwise_phase(*args,anchor=15,
                minimum_distinct_signatures=1)
        self.assertEqual(explicit['contigs'][0]['classification'],
                         'observed_direct_pair_phase')

    def test_phase_threshold_must_be_positive_integer_not_boolean(self):
        truth,r1,r2=self.experiment(pair_count=2)
        for invalid in (0,-1,True,1.5):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                audit_pairwise_phase(
                    r1,r2,truth['phase_coupled_haplotypes'][0],(400,600),[],
                    minimum_distinct_signatures=invalid)

    def test_invalid_geometry_rejected(self):
        truth, r1, r2 = self.experiment(pair_count=2)
        for pos in ((900, 400), (0, 600), (400, 1400)):
            with self.subTest(pos=pos), self.assertRaises(ValueError):
                audit_pairwise_phase(r1, r2, truth["phase_coupled_haplotypes"][0],
                                     pos, [])
