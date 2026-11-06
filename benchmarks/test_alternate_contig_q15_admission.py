"""Tests for original-paired-FASTQ Q15 alternate-contig admission."""
import tempfile
import unittest
from pathlib import Path

from alternate_contig_q15_admission import screen_contigs


class AlternateContigQ15AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Create a reference with no novel 31-mer
        self.ref = self.root / "ref.fasta"
        self.ref.write_text(">ref1\n" + "A" * 200 + "\n")
        # Create candidate with a novel 31-mer
        self.cand = self.root / "cand.fasta"
        # Make a contig that has "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC" as a novel 31-mer
        self.novel = "C" * 31
        self.cand.write_text(">ivanka_1\n" + "A" * 100 + self.novel + "A" * 100 + "\n")
        self.r1 = self.root / "R1.fastq"
        self.r2 = self.root / "R2.fastq"

    def write_pairs_with_novel(self, n_pairs, same_pair_signature=False):
        with self.r1.open("w") as f1, self.r2.open("w") as f2:
            for i in range(n_pairs):
                if same_pair_signature:
                    seq1 = "G" * 10 + self.novel + "T" * 20
                    seq2 = "A" * 50 + "G" * 20
                else:
                    pad = "G" * 10
                    seq1 = pad + self.novel + "T" * (20 + i)
                    seq2 = "A" * (50 + i) + "G" * (20 + i)
                q1 = "I" * len(seq1)
                q2 = "I" * len(seq2)
                f1.write(f"@pair{i}/1\n{seq1}\n+\n{q1}\n")
                f2.write(f"@pair{i}/2\n{seq2}\n+\n{q2}\n")

    def test_requires_five_qnames_and_five_signatures(self):
        self.write_pairs_with_novel(3, same_pair_signature=False)
        res = screen_contigs(self.cand, self.r1, self.r2, [self.ref])
        self.assertFalse(res["results"][0]["admitted"])
        self.write_pairs_with_novel(5, same_pair_signature=False)
        res = screen_contigs(self.cand, self.r1, self.r2, [self.ref])
        self.assertTrue(res["results"][0]["admitted"])

    def test_same_signature_does_not_count(self):
        self.write_pairs_with_novel(5, same_pair_signature=True)
        res = screen_contigs(self.cand, self.r1, self.r2, [self.ref])
        # Only 1 distinct signature even if 5 qnames
        self.assertFalse(res["results"][0]["admitted"])

    def test_rejects_if_novel_not_in_reads(self):
        # Write reads without the novel kmer
        with self.r1.open("w") as f1, self.r2.open("w") as f2:
            for i in range(5):
                f1.write(f"@pair{i}/1\n{'A'*80}\n+\n{'I'*80}\n")
                f2.write(f"@pair{i}/2\n{'T'*80}\n+\n{'I'*80}\n")
        res = screen_contigs(self.cand, self.r1, self.r2, [self.ref])
        self.assertFalse(res["results"][0]["admitted"])

    def test_q15_quality_required(self):
        # Write pairs but with low quality on the novel kmer
        with self.r1.open("w") as f1, self.r2.open("w") as f2:
            for i in range(5):
                pad = "G" * (10)
                seq1 = pad + self.novel + "T" * (20 + i)
                seq2 = "A" * (50 + i) + "G" * (20 + i)
                q1 = "I" * 10 + "/" * 31 + "I" * (20 + i)  # Q14
                q2 = "I" * len(seq2)
                f1.write(f"@pair{i}/1\n{seq1}\n+\n{q1}\n")
                f2.write(f"@pair{i}/2\n{seq2}\n+\n{q2}\n")
        res = screen_contigs(self.cand, self.r1, self.r2, [self.ref])
        self.assertFalse(res["results"][0]["admitted"])

    def test_no_novel_kmer_rejected(self):
        cand2 = self.root / "cand2.fasta"
        cand2.write_text(">ivanka_1\n" + "A" * 200 + "\n")  # all from ref
        self.write_pairs_with_novel(10)
        res = screen_contigs(cand2, self.r1, self.r2, [self.ref])
        self.assertFalse(res["results"][0]["admitted"])


if __name__ == "__main__":
    unittest.main()
