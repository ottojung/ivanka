"""Tests for orientation-independent, exact k-mer retention auditing."""
import random
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contig_diversity import audit, canonical_kmers, canonical_linkages, read_fasta, read_record_support, read_supported_loss, read_linkage_loss


class ContigDiversityTest(unittest.TestCase):
    def test_identical_and_reverse_complement_are_preserved(self):
        rng = random.Random(12)
        seq = "".join(rng.choices("ACGT", k=150))
        rc = seq.translate(str.maketrans("ACGT", "TGCA"))[::-1]
        for after in ([seq], [rc]):
            report = audit([seq], after)
            self.assertEqual(report["exact_old_contigs_retained"], 1)
            self.assertEqual(report["old_kmers_lost"], 0)
            self.assertEqual(report["old_kmer_retention_fraction"], 1)

    def test_distinct_contig_loss_is_detected(self):
        old = ["A" * 35 + "C" * 35, "T" * 35 + "G" * 35]
        report = audit(old, [old[0]], k=9)
        self.assertGreater(report["old_kmers_lost"], 0)
        self.assertLess(report["old_kmer_retention_fraction"], 1)
        self.assertEqual(report["exact_old_contigs_retained"], 1)

    def test_duplicate_old_contigs_count_as_entries(self):
        report = audit(["ACGTACGT", "ACGTACGT"], ["ACGTACGT"], k=4)
        self.assertEqual(report["exact_old_contigs_retained"], 2)

    def test_ambiguous_bases_and_short_sequences(self):
        self.assertEqual(canonical_kmers("NNACGTN", 4), {"ACGT"})
        report = audit(["N", "ACG"], ["N"], 4)
        self.assertIsNone(report["old_kmer_retention_fraction"])
        self.assertEqual(report["old_kmers_lost"], 0)
        with self.assertRaises(ValueError):
            audit(["ACGT"], [], 0)

    def test_read_support_counts_distinct_fastq_records(self):
        with tempfile.TemporaryDirectory() as temp:
            r1, r2 = Path(temp) / "r1.fastq", Path(temp) / "r2.fastq"
            r1.write_text("@read1\nACGTACGT\n+\n!!!!!!!!\n")
            r2.write_text("@read1\nTTTTTTTT\n+\n!!!!!!!!\n")
            support, sampled = read_record_support([r1, r2], {"ACGT"}, k=4)
            self.assertEqual(sampled, 2)
            self.assertEqual(support["ACGT"], 1)  # two hits, one read record
            report = read_supported_loss(["ACGTACGT"], ["TTTTTTTT"], [r1, r2], k=4)
            self.assertGreater(report["lost_unique_kmers"], 0)
            self.assertGreater(report["lost_kmers_supported_by_at_least_1_record"], 0)
            self.assertEqual(report["sampled_read_records"], 2)

    def test_bad_fastq_or_mismatched_pair_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.fastq", Path(temp) / "b.fastq"
            a.write_text("@x\nACGT\n+\n!!!!\n")
            b.write_text("")
            with self.assertRaisesRegex(ValueError, "equal sampled"):
                read_record_support([a, b], {"ACGT"}, k=4)
            b.write_text("@x\nACGT\n+\n!!!\n")
            with self.assertRaisesRegex(ValueError, "invalid/truncated"):
                read_record_support([a, b], {"ACGT"}, k=4)
            with self.assertRaises(ValueError):
                read_record_support([a, a], {"ACGT"}, k=4, max_records=0)

    def test_read_linkage_detects_phase_loss_in_spite_of_full_31mer_retention(self):
        old = "A" * 60 + "C" * 60 + "A" * 60
        new = "C" * 60 + "A" * 60 + "C" * 60
        self.assertEqual(audit([old], [new], 31)["old_kmers_lost"], 0)
        self.assertGreater(len(canonical_linkages(old, 31, 100) -
                               canonical_linkages(new, 31, 100)), 0)
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.fastq", Path(temp) / "b.fastq"
            a.write_text("@pair/1\n" + old + "\n+\n" + "!" * len(old) + "\n")
            b.write_text("@pair/2\n" + "T" * len(old) + "\n+\n" +
                         "!" * len(old) + "\n")
            report = read_linkage_loss([old], [new], [a, b], distances=[100], k=31)
            self.assertEqual(report["sampled_read_records"], 2)
            self.assertGreater(report["distances"]["100"]["lost_linkages_supported_by_at_least_1_record"], 0)

    def test_linkage_reverse_complement_and_bad_distances(self):
        seq = "ACGTACGTTGCAACCTGATCGTACGCTAGCTTGAGCTAGGCTACGAT"
        rc = seq.translate(str.maketrans("ACGT", "TGCA"))[::-1]
        self.assertEqual(canonical_linkages(seq, 7, 17),
                         canonical_linkages(rc, 7, 17))
        self.assertEqual(canonical_linkages("ACNNNNGT", 2, 5), set())
        with self.assertRaises(ValueError):
            canonical_linkages(seq, 31, 0)
        with self.assertRaises(ValueError):
            read_linkage_loss([seq], [rc], [], distances=[-1])

    def test_cli_passes_custom_k_to_linkage_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            old, new = folder / "old.fa", folder / "new.fa"
            r1, r2 = folder / "r1.fq", folder / "r2.fq"
            old.write_text(">old\nAAAACCCCAAAA\n")
            new.write_text(">new\nCCCCAAAACCCC\n")
            for path in (r1, r2):
                path.write_text("@x\nAAAACCCCAAAA\n+\n!!!!!!!!!!!!\n")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("contig_diversity.py")),
                 str(old), str(new), "--k", "4", "--reads1", str(r1),
                 "--reads2", str(r2), "--link-distances", "5"],
                capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["lost_read_linkages"]["k"], 4)

    def test_fasta_multiline_and_missing_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.fasta"
            path.write_text(">first note\nACGT\nACGT\n>second\nNNNN\n")
            self.assertEqual(read_fasta(path), ["ACGTACGT", "NNNN"])
            path.write_text("ACGT\n")
            with self.assertRaises(ValueError):
                read_fasta(path)


if __name__ == "__main__":
    unittest.main()
