"""Focused CPU-only tests for raw paired-read allele provenance."""
import gzip
import tempfile
import unittest
from pathlib import Path

from raw_fastq_block_support import audit_original_pairs, reverse_complement


def record(name, sequence, quality=None):
    return f"@{name}\n{sequence}\n+\n{quality or 'I' * len(sequence)}\n"


class RawFastqBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.r1 = Path(self.tmp.name) / "r1.fastq.gz"
        self.r2 = Path(self.tmp.name) / "r2.fastq.gz"

    def write(self, left, right):
        for path, rows in ((self.r1, left), (self.r2, right)):
            with gzip.open(path, "wt") as stream:
                stream.write("".join(rows))

    def audit(self, alleles=("ACGTAC",), quality=15):
        return audit_original_pairs(self.r1, self.r2, alleles, quality)

    def test_both_mates_are_one_pair(self):
        self.write([record("p/1", "TTACGTACGG")],
                   [record("p/2", "CCACGTACAA")])
        result = self.audit()
        self.assertEqual(result["read_pairs"], 1)
        self.assertEqual(result["allele_support_pair_ids"]["ACGTAC"], 1)
        self.assertEqual(result["allele_distinct_pair_sequences"]["ACGTAC"], 1)

    def test_identical_pair_sequences_are_not_distinct(self):
        self.write([record("p1", "TTACGTACGG"), record("p2", "TTACGTACGG")],
                   [record("p1", "CCCCCCCCCC"), record("p2", "CCCCCCCCCC")])
        result = self.audit()
        self.assertEqual(result["allele_support_pair_ids"]["ACGTAC"], 2)
        self.assertEqual(result["allele_distinct_pair_sequences"]["ACGTAC"], 1)

    def test_reverse_complement_is_observed(self):
        allele = "AACGTT"
        self.write([record("p", "CC" + reverse_complement(allele) + "GG")],
                   [record("p", "CCCCCCCCCC")])
        self.assertEqual(self.audit((allele,))["allele_support_pair_ids"][allele], 1)

    def test_quality_gate_applies_to_every_allele_base(self):
        self.write([record("p", "TTACGTACGG", "IIIII!IIII")],
                   [record("p", "CCCCCCCCCC")])
        self.assertEqual(self.audit()["allele_support_pair_ids"]["ACGTAC"], 0)

    def test_conflicting_pair_support_is_excluded(self):
        self.write([record("p", "ACGTACGGGGGG")],
                   [record("p", "TTTTTTGGGGGG")])
        result = self.audit(("ACGTAC", "TTTTTT"))
        self.assertEqual(result["conflicting_pair_ids"], 1)
        self.assertEqual(sum(result["allele_support_pair_ids"].values()), 0)

    def test_low_quality_duplicate_signature_is_conservative(self):
        self.write([record("p1", "TTACGTACGG"), record("p2", "TTACGTACGG", "!!!!!!!!!!")],
                   [record("p1", "CCCCCCCCCC"), record("p2", "CCCCCCCCCC")])
        result = self.audit()
        self.assertEqual(result["allele_support_pair_ids"]["ACGTAC"], 1)
        self.assertEqual(result["allele_distinct_pair_sequences"]["ACGTAC"], 0)

    def test_missing_mate_fails(self):
        self.write([record("p", "TTACGTACGG")], [])
        with self.assertRaises(ValueError):
            self.audit()

    def test_mismatched_ids_fail(self):
        self.write([record("p", "TTACGTACGG")],
                   [record("q", "CCCCCCCCCC")])
        with self.assertRaises(ValueError):
            self.audit()

    def test_duplicate_qname_fails(self):
        self.write([record("p", "TTACGTACGG")] * 2,
                   [record("p", "CCCCCCCCCC")] * 2)
        with self.assertRaises(ValueError):
            self.audit()

    def test_invalid_inputs_fail(self):
        self.write([record("p", "TTACGTACGG")],
                   [record("p", "CCCCCCCCCC")])
        for alleles, q in (((), 15), (("NNN",), 15),
                           (("ACGTAC", "ACGTAC"), 15),
                           (("AACGTT", "AACGTT"), 15),
                           (("AACG", "CGTT"), 15), (("ACGTAC",), -1)):
            with self.assertRaises(ValueError):
                self.audit(alleles, q)

    def test_malformed_quality_fails(self):
        self.write([record("p", "TTACGTACGG", "II")],
                   [record("p", "CCCCCCCCCC")])
        with self.assertRaises(ValueError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
