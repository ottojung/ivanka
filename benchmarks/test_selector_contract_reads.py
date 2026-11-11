"""Original paired-read observations are invariant under irrelevant presentation."""
import tempfile
import unittest

from selector_contract_fixtures import sample_reads
from ivanka_read_support_selector import read_supported_ranking


class ReadSupportObservations(unittest.TestCase):
    def test_mate_order_does_not_change_support(self):
        with tempfile.TemporaryDirectory() as folder:
            sequence, (r1, r2) = sample_reads(folder)
            entries = [(">same", sequence)]
            self.assertEqual(read_supported_ranking(entries, (r1,r2)),
                             read_supported_ranking(entries, (r2,r1)))

    def test_candidate_header_does_not_influence_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder)
            a = read_supported_ranking([(">alpha",seq)], reads)
            b = read_supported_ranking([(">completely-different",seq)], reads)
            self.assertEqual(a,b)

    def test_compression_preserves_read_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, plain = sample_reads(folder)
            baseline = read_supported_ranking([(">x",seq)], plain, with_depth=True)
            _, compressed = sample_reads(folder, zipped=True)
            self.assertEqual(baseline, read_supported_ranking([(">x",seq)], compressed, with_depth=True))

    def test_max_pairs_limits_count_without_inventing_support(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder, count=40)
            full = read_supported_ranking([(">x",seq)], reads)
            first = read_supported_ranking([(">x",seq)], reads, max_pairs=10)
            self.assertLessEqual(first[2][0],10)
            self.assertLessEqual(first[2][0],full[2][0])

    def test_no_original_pairs_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder, count=0)
            with self.assertRaises(ValueError):
                read_supported_ranking([(">x",seq)], reads)
