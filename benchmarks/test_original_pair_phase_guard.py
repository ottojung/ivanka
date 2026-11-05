"""Direct Q15 phase evidence is useful only when pairs actually bridge loci."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from original_pair_phase_guard import evaluate, screen_fasta
from original_pair_phase_calls import context_index
from snv_q15_fastq import iter_original_pairs
from synthetic_phase_pairs import generate


class OriginalPairPhaseVetoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory()
        cls.root = Path(cls.storage.name)
        cls.linked = generate(
            cls.root / "linked", variants=(280, 400),
            pairs_per_haplotype=500, seed=17, error_rate=0.002)
        cls.unlinked = generate(
            cls.root / "unlinked", variants=(280, 900),
            pairs_per_haplotype=500, seed=17, error_rate=0.002)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def screen(self, name, sequence, anchor=7, **kwargs):
        root = self.root / name
        return screen_fasta(
            [("candidate", sequence)],
            root / "synthetic_R1.fastq.gz",
            root / "synthetic_R2.fastq.gz",
            max_pairs=1000, anchor=anchor, **kwargs)["results"][0]

    def recombinant(self, truth):
        a, b = truth["phase_coupled_haplotypes"]
        pos = truth["variant_positions_zero_based"][-1]
        seq = list(a)
        seq[pos] = b[pos]
        return "".join(seq)

    def test_true_haplotype_is_not_flagged_when_linked(self):
        self.assertGreater(
            self.linked["read_pairs_directly_observing_both_variants"], 0)
        original = self.linked["phase_coupled_haplotypes"][0]
        result = self.screen("linked", original)
        self.assertFalse(result["withhold_contig_as_unverified_phase"])
        self.assertEqual(result["variant_sites_zero_based"], [280, 400])
        self.assertEqual(result["direct_pair_observations"][0][
            "phase_evidence_status"], "direct_contig_combination_observed")
        self.assertGreater(result["direct_pair_observations"][0][
            "direct_original_pair_support_for_contig_alleles"], 0)

    def test_recombinant_is_flagged_only_with_genuine_q15_bridges(self):
        result = self.screen("linked", self.recombinant(self.linked))
        self.assertEqual(result["contradictory_direct_variant_pairs"],
                         [[280, 400]])
        observed = result["direct_pair_observations"][0]
        self.assertTrue(observed["contradictory_direct_link"])
        self.assertEqual(observed["direct_original_pair_support_for_contig_alleles"], 0)
        self.assertGreaterEqual(max(item["original_pairs"] for item in
                                    observed["other_direct_allele_combinations"]), 5)
        self.assertEqual(observed["phase_evidence_status"], "direct_conflict_observed")
        self.assertFalse(result["independent_physical_molecule_identity_proven"])

    def test_long_31mer_context_discards_actual_linkage(self):
        seq = self.recombinant(self.linked)
        long = self.screen("linked", seq, anchor=15)
        short = self.screen("linked", seq, anchor=7)
        self.assertFalse(long["withhold_contig_as_unverified_phase"])
        self.assertEqual(long["direct_pair_observations"][0][
            "any_original_pair_both_sites_at_q15"], 0)
        self.assertTrue(short["withhold_contig_as_unverified_phase"])
        self.assertGreater(short["direct_pair_observations"][0][
            "any_original_pair_both_sites_at_q15"], 0)

    def test_unlinked_alternative_phase_is_unknown_not_vetoed_or_certified(self):
        self.assertEqual(self.unlinked["read_pairs_directly_observing_both_variants"], 0)
        for seq in (self.unlinked["phase_coupled_haplotypes"][0],
                    self.recombinant(self.unlinked)):
            with self.subTest(first_15=seq[:15]):
                result = self.screen("unlinked", seq)
                self.assertFalse(result["withhold_contig_as_unverified_phase"])
                evidence = result["direct_pair_observations"][0]
                self.assertEqual(evidence["any_original_pair_both_sites_at_q15"], 0)
                self.assertEqual(evidence["phase_evidence_status"],
                                 "unresolved_no_contig_allele_bridge")
                self.assertTrue(result["no_detected_conflict_does_not_validate_haplotype"])

    def test_duplicate_original_qname_and_contig_limit_fail_closed(self):
        seq = self.linked["phase_coupled_haplotypes"][0]
        source = self.root / "linked"
        limited = screen_fasta(
            [("first", seq), ("second", seq)],
            source/"synthetic_R1.fastq.gz", source/"synthetic_R2.fastq.gz",
            max_pairs=1000, max_contigs=1)
        self.assertEqual(limited["screened_contig_count"], 1)
        self.assertEqual(limited["reference_scope_contig_count"], 2)
        self.assertGreater(limited["results"][0][
            "excluded_ambiguous_cross_contig_contexts"], 0)
        data = [(name, r1, r2) for name,r1,r2 in
                iter_original_pairs(source/"synthetic_R1.fastq.gz",
                                    source/"synthetic_R2.fastq.gz",max_pairs=2)]
        self.assertEqual(len(data), 2)
        self.assertTrue(all(len(pair[1][0]) == 100 for pair in data))

    def test_other_homologous_contig_vetoes_context_placement(self):
        # Same local Q15 window shared across alternative haplotypes cannot
        # uniquely identify an original source contig, even for known truth.
        seq = self.linked["phase_coupled_haplotypes"][0]
        source = self.root / "linked"
        report = screen_fasta(
            [("reported", seq), ("other_homologous", seq)],
            source/"synthetic_R1.fastq.gz",
            source/"synthetic_R2.fastq.gz",
            max_pairs=1000, anchor=7, max_contigs=1)
        result = report["results"][0]
        self.assertEqual(report["reference_scope_contig_count"], 2)
        self.assertEqual(report["screened_contig_count"], 1)
        self.assertEqual(result["variant_sites_zero_based"], [])
        self.assertFalse(result["withhold_contig_as_unverified_phase"])
        self.assertGreater(result["excluded_ambiguous_cross_contig_contexts"], 0)

    def test_q14_contexts_cannot_supply_a_phase_conflict(self):
        seq = self.recombinant(self.linked)
        root = self.root / "linked"
        calls = []
        for _, r1, r2 in iter_original_pairs(
                root/"synthetic_R1.fastq.gz",
                root/"synthetic_R2.fastq.gz", max_pairs=1000):
            calls.append(((r1[0],r2[0]),
                          (r1[0], "/"*len(r1[1])),
                          (r2[0], "/"*len(r2[1]))))
        report = evaluate(seq,calls,anchor=7)
        self.assertEqual(report["variant_sites_zero_based"], [])
        self.assertFalse(report["withhold_contig_as_unverified_phase"])

    def test_cli_requires_externally_pinned_originals_and_private_output(self):
        truth = self.linked
        fasta = self.root / "candidate.fasta"
        seq = self.recombinant(truth)
        fasta.write_text(f">candidate len={len(seq)}\n{seq}\n")
        source = self.root / "linked"
        r1, r2 = [source / f"synthetic_R{i}.fastq.gz" for i in (1, 2)]
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (fasta, r1, r2)]
        script = Path(__file__).with_name("original_pair_phase_guard.py")
        with tempfile.TemporaryDirectory() as separate:
            output = Path(separate) / "phase-status.json"
            cmd = [sys.executable, str(script), str(fasta), str(r1), str(r2),
                   "--sha256-fasta", hashes[0], "--sha256-r1", hashes[1],
                   "--sha256-r2", hashes[2], "--max-pairs", "1000",
                   "--anchor", "7", "--output", str(output)]
            valid = subprocess.run(cmd, capture_output=True, text=True,
                                   check=False)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            data = json.loads(output.read_text())
            self.assertEqual(data["source_sha256"]["fasta"], hashes[0])
            self.assertTrue(data["original_sources_verified_before_and_after"])
            self.assertTrue(data["results"][0]["withhold_contig_as_unverified_phase"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            bad = cmd.copy()
            bad[bad.index("--sha256-r1") + 1] = "0" * 64
            bad[-1] = str(Path(separate) / "should-not-exist.json")
            rejected = subprocess.run(bad, capture_output=True, text=True,
                                      check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(Path(bad[-1]).exists())

    def test_unique_context_and_invalid_anchor_bound(self):
        seq = self.linked["phase_coupled_haplotypes"][0]
        idx = context_index(seq, anchor=7)
        self.assertGreater(len(idx), 100)
        with self.assertRaisesRegex(ValueError, "five"):
            context_index(seq, anchor=4)
        with self.assertRaisesRegex(ValueError, "integer"):
            evaluate(seq, [], anchor=True)
        with self.assertRaisesRegex(ValueError, "integer"):
            evaluate(seq, [], anchor=16)


if __name__ == "__main__":
    unittest.main()
