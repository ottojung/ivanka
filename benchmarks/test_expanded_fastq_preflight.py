"""Synthetic data must be natively readable by MiCall before any benchmark run."""
import gzip
import unittest
import tempfile
from pathlib import Path

from expanded.fastq_preflight import verify_pairs


def fastq(path, mate, *, name="p", casava=True, quality="IIII"):
    header = (f"@M00123:1:FCX:1:1101:{name}:1000 {mate}:N:0:1"
              if casava else f"@{name}/{mate}")
    with gzip.open(path, "wt") as stream:
        stream.write(f"{header}\nACGT\n+\n{quality}\n")


class FastqPreflightTests(unittest.TestCase):
    def test_compatible_casava_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b = Path(folder)/"a.gz", Path(folder)/"b.gz"
            fastq(a,1)
            fastq(b,2)
            self.assertEqual(verify_pairs(a,b,1), 1)

    def test_rejects_old_synthetic_header_before_micall(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b = Path(folder)/"a.gz", Path(folder)/"b.gz"
            fastq(a,1,casava=False)
            fastq(b,2,casava=False)
            with self.assertRaisesRegex(ValueError, "CASAVA"):
                verify_pairs(a,b,1)

    def test_mate_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b = Path(folder)/"a.gz", Path(folder)/"b.gz"
            fastq(a,1,name="a")
            fastq(b,2,name="b")
            with self.assertRaisesRegex(ValueError, "mate"):
                verify_pairs(a,b,1)

    def test_unequal_pair_counts_and_quality(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b = Path(folder)/"a.gz", Path(folder)/"b.gz"
            fastq(a,1)
            fastq(b,2,quality="III")
            with self.assertRaisesRegex(ValueError, "quality"):
                verify_pairs(a,b,1)
            fastq(b,2)
            with self.assertRaisesRegex(ValueError, "pair count"):
                verify_pairs(a,b,2)


if __name__ == "__main__":
    unittest.main()
