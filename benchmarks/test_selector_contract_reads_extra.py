"""Depth estimates count observations, never independently verified molecules."""
import tempfile
import unittest

from selector_contract_fixtures import sample_reads
from ivanka_read_support_selector import K, index_kmers, read_supported_ranking


class ReadSupportDepth(unittest.TestCase):
    def test_depth_vector_matches_candidate_window_count(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder)
            _, _, _, depths = read_supported_ranking([(">x",seq)], reads, with_depth=True)
            self.assertEqual(len(depths[0]),len(seq)-K+1)

    def test_repeated_reads_count_additional_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder)
            original = read_supported_ranking([(">x",seq)], reads, with_depth=True)
            seq, reads = sample_reads(folder, count=80)
            repeated = read_supported_ranking([(">x",seq)], reads, with_depth=True)
            self.assertGreater(repeated[2][0], original[2][0])
            self.assertGreater(sum(repeated[3][0]), sum(original[3][0]))

    def test_ambiguous_candidate_windows_are_not_indexed(self):
        seq = "A"*40 + "N"*31 + "C"*40
        kmers = index_kmers([(">ambiguous",seq)])
        self.assertNotIn("N"*K,kmers)

    def test_reverse_complement_matches_original_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, reads = sample_reads(folder)
            rev = seq.translate(str.maketrans("ACGT","TGCA"))[::-1]
            original = read_supported_ranking([(">x",seq)], reads)
            flipped = read_supported_ranking([(">x",rev)], reads)
            self.assertEqual(original,flipped)

    def test_missing_mate_records_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            seq, (r1,r2) = sample_reads(folder)
            r2.write_text("")
            with self.assertRaises(ValueError):
                read_supported_ranking([(">x",seq)], (r1,r2))
