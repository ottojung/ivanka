"""Strict original-pair Q15 evidence and falsification tests."""
import hashlib
import json
import os
import random
import tempfile
import unittest
from pathlib import Path

from snv_original_fastq_q15 import audit, private_output
from snv_q15_evidence import reverse_complement


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OriginalFastqSNVTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        rng = random.Random(408)
        self.parent = "".join(rng.choices("ACGT", k=101))
        self.pos = 50
        self.base = self.parent[self.pos]
        self.alt = next(b for b in "ACGT" if b != self.base)
        self.context = self.parent[20:50] + self.alt + self.parent[51:81]
        self.alt31 = self.context[15:46]
        self.ref31 = self.alt31[:15] + self.base + self.alt31[16:]
        self.fasta = self.root / "ordinary.fasta"
        self.fasta.write_text(f">ivanka_1 len=101\n{self.parent}\n")
        self.tsv = self.root / "audit.tsv"
        self.tsv.write_text(
            "#schema=ivanka.unphased_snv_candidates.v1\n"
            "#phasing=unidentified; independent_dna_molecules=false\n"
            "#sampling=first_50000_pairs_every_third_31mer; kmer_counts_are_occurrences_not_molecules; phred_unchecked=true\n"
            "#ordinary_micall_fasta_unchanged=true\n"
            "parent_fasta_index\tlength\tsnv_offset_zero_based\tbaseline_base\talternate_base\tassembling_read_record_support\tnovel_sampled_31mers_ge5\tlocal_61base_unphased_context\n"
            f"1\t101\t50\t{self.base}\t{self.alt}\t120\t7\t{self.context}\n"
        )
        self.r1 = self.root / "R1.fastq"
        self.r2 = self.root / "R2.fastq"
        self.make_reads([(self.alt31, "I" * 31, "T" * 35, "I" * 35),
                         (self.ref31, "I" * 31, "A" * 35, "I" * 35)])
        self.refresh_hashes()

    def make_reads(self, records):
        with self.r1.open("w") as f1, self.r2.open("w") as f2:
            for i, (s1, q1, s2, q2) in enumerate(records):
                for stream, mate, seq, qual in ((f1, 1, s1, q1),
                                                (f2, 2, s2, q2)):
                    stream.write(f"@pair{i}/{mate}\n{seq}\n+\n{qual}\n")

    def refresh_hashes(self):
        self.hashes = {key: digest(path)
                       for key, path in (("audit_tsv", self.tsv),
                                         ("ordinary_fasta", self.fasta),
                                         ("original_r1", self.r1),
                                         ("original_r2", self.r2))}

    def run_audit(self, **overrides):
        opts = dict(expected_hashes=self.hashes, min_pairs=1)
        opts.update(overrides)
        return audit(self.tsv, self.fasta, self.r1, self.r2, **opts)

    def test_two_exact_q15_alleles_count_one_original_pair_each(self):
        result = self.run_audit()
        self.assertEqual(result["pairs_scanned"], 2)
        row = result["candidates"][0]
        self.assertEqual(row["q15_original_pairs_observing_alternative"], 1)
        self.assertEqual(row["q15_original_pairs_observing_reference"], 1)
        self.assertEqual(row["q15_original_pairs_with_both_alleles"], 0)
        self.assertEqual(row["q15_distinct_consistent_paired_sequences_alternative"], 1)
        self.assertTrue(row["candidate_meets_local_q15_screen"])
        self.assertFalse(result["original_pair_ids_are_independent_physical_molecules"])
        self.assertFalse(result["full_length_haplotype_phase_inferred"])

    def test_rc_mate_and_quality_veto_and_pair_conflict(self):
        low = "I" * 15 + "/" + "I" * 15  # Q14 at variant
        self.make_reads([
            (reverse_complement(self.alt31), "I" * 31, "T" * 35, "I" * 35),
            (self.alt31, low, "G" * 35, "I" * 35),
            (self.alt31, "I" * 31, self.ref31, "I" * 31),
            (self.ref31, "I" * 31, self.ref31, "I" * 31),
        ])
        self.refresh_hashes()
        row = self.run_audit()["candidates"][0]
        self.assertEqual(row["q15_original_pairs_observing_alternative"], 1)
        self.assertEqual(row["q15_original_pairs_observing_reference"], 1)
        self.assertEqual(row["q15_original_pairs_with_both_alleles"], 1)
        self.assertEqual(row["q15_original_pairs_without_exact_31mer"], 1)

    def test_duplicate_sequence_signatures_with_partial_calls_vetoed(self):
        self.make_reads([
            (self.alt31, "I" * 31, "G" * 35, "I" * 35),
            (self.alt31, "/" * 31, "G" * 35, "I" * 35),
        ])
        self.refresh_hashes()
        row = self.run_audit()["candidates"][0]
        self.assertEqual(row["q15_original_pairs_observing_alternative"], 1)
        self.assertEqual(row["q15_distinct_consistent_paired_sequences_alternative"], 0)
        self.assertEqual(row[
            "paired_sequence_signatures_with_inconsistent_or_missing_observation"], 1)
        self.assertFalse(row["candidate_meets_local_q15_screen"])

    def test_repeated_31mer_in_same_parent_blocks_positional_qualification(self):
        # Even direct high-quality alternative reads cannot identify which
        # of many same-31mer positions in a repeated contig is the source.
        parent = "A" * 101
        context = "A" * 30 + "C" + "A" * 30
        self.fasta.write_text(">ivanka_1 len=101\n" + parent + "\n")
        self.tsv.write_text(self.tsv.read_text()
                            .replace(self.context, context)
                            .replace(f"\t{self.base}\t{self.alt}\t",
                                     "\tA\tC\t"))
        alt = "A" * 15 + "C" + "A" * 15
        self.make_reads([(alt, "I" * 31, "G" * 35, "I" * 35)
                         for _ in range(12)])
        self.refresh_hashes()
        row = self.run_audit()["candidates"][0]
        self.assertEqual(row["q15_original_pairs_observing_alternative"], 12)
        self.assertGreater(row["reference_31mer_hits_in_own_parent"], 1)
        self.assertFalse(row["exact_31mer_uniquely_locates_offset_in_parent"])
        self.assertFalse(row["candidate_meets_local_q15_screen"])

    def test_alternative_already_in_other_contig_blocks_novelty_claim(self):
        self.fasta.write_text(self.fasta.read_text() +
                              f">ivanka_2 len=61\n{self.context}\n")
        self.refresh_hashes()
        row = self.run_audit()["candidates"][0]
        self.assertEqual(row["alternative_31mer_hits_in_ordinary_contigs"], 1)
        self.assertFalse(row["candidate_meets_local_q15_screen"])

    def test_duplicate_qname_or_mismatched_mates_fail(self):
        self.make_reads([
            (self.alt31, "I" * 31, "G" * 35, "I" * 35),
            (self.alt31, "I" * 31, "G" * 35, "I" * 35),
        ])
        content = self.r1.read_text().replace("@pair1/1", "@pair0/1")
        self.r1.write_text(content)
        self.r2.write_text(self.r2.read_text().replace("@pair1/2", "@pair0/2"))
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "Duplicate original"):
            self.run_audit()
        self.r2.write_text(self.r2.read_text().replace("@pair0/2", "@mismatch/2", 1))
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "identities disagree"):
            self.run_audit()

    def test_bad_external_hash_tampered_context_and_declared_length(self):
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.run_audit(expected_hashes=dict(self.hashes, original_r1="0" * 64))
        changed = self.tsv.read_text().replace(self.context, "A" * 61)
        self.tsv.write_text(changed)
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.run_audit()
        self.tsv.write_text(self.tsv.read_text().replace("A" * 61, self.context))
        self.fasta.write_text(self.fasta.read_text().replace("len=101", "len=100"))
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "declared length"):
            self.run_audit()

    def test_malformed_quality_and_incomplete_pair_fail_closed(self):
        self.r1.write_text(self.r1.read_text()[:-2])
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "Malformed original"):
            self.run_audit()
        self.make_reads([(self.alt31, "I" * 31, "G" * 35, "I" * 35)])
        self.r2.write_text("")
        self.refresh_hashes()
        with self.assertRaisesRegex(ValueError, "Unequal original"):
            self.run_audit()

    def test_threshold_and_source_protected_private_write(self):
        self.assertFalse(self.run_audit(min_pairs=2)["candidates"][0][
            "candidate_meets_local_q15_screen"])
        for params in ({"min_phred": 14}, {"max_pairs": 50001},
                       {"min_pairs": 0}, {"min_pairs": True}):
            with self.assertRaisesRegex(ValueError, "Invalid research"):
                self.run_audit(**params)
        report = self.run_audit()
        with tempfile.TemporaryDirectory() as safe_dir:
            output = Path(safe_dir) / "report.json"
            private_output(report, output, [self.tsv, self.fasta, self.r1, self.r2])
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                private_output(report, output, [self.tsv, self.fasta, self.r1, self.r2])
        with self.assertRaisesRegex(ValueError, "original evidence"):
            private_output(report, self.root / "report.json",
                           [self.tsv, self.fasta, self.r1, self.r2])


if __name__ == "__main__":
    unittest.main()
