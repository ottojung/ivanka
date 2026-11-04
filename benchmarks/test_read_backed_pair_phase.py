"""Original paired reads, not generating haplotype labels, veto false phase."""
import gzip
import tempfile
import unittest
from pathlib import Path

from read_backed_pair_phase import audit_pairwise_phase
from synthetic_phase_pairs import generate


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

    def test_invalid_geometry_rejected(self):
        truth, r1, r2 = self.experiment(pair_count=2)
        for pos in ((900, 400), (0, 600), (400, 1400)):
            with self.subTest(pos=pos), self.assertRaises(ValueError):
                audit_pairwise_phase(r1, r2, truth["phase_coupled_haplotypes"][0],
                                     pos, [])
