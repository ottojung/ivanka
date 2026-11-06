"""Duplicates, incomplete copies and conflicts are not independent evidence."""
import unittest

from original_pair_locus_signatures import consistent_locus_signatures


class OriginalPairLocusSignatureTests(unittest.TestCase):
    def test_repeated_original_sequence_counts_once_per_allele_and_group(self):
        records = [(('R1', 'R2'), {0:'A', 1:'C'}) for _ in range(12)]
        observed = consistent_locus_signatures(records)
        self.assertEqual(observed[0]['A'], 1)
        self.assertEqual(observed[1]['C'], 1)

    def test_missing_q15_call_in_one_duplicate_vetoes_entire_signature(self):
        records = [
            (('R1', 'R2'), {0:'A', 1:'C'}),
            (('R1', 'R2'), {0:'A'}),
            (('R3', 'R4'), {0:'T', 1:'G'}),
        ]
        observed = consistent_locus_signatures(records)
        self.assertEqual(observed[0]['A'], 1)
        self.assertEqual(observed[1]['C'], 0)
        self.assertEqual(observed[0]['T'], 1)
        self.assertEqual(observed[1]['G'], 1)

    def test_inconsistent_alleles_in_identical_sequence_group_are_excluded(self):
        records = [
            (('R1', 'R2'), {0:'A'}),
            (('R1', 'R2'), {0:'G'}),
            (('R3', 'R4'), {0:'C'}),
        ]
        observed = consistent_locus_signatures(records)
        self.assertEqual(observed[0]['A'], 0)
        self.assertEqual(observed[0]['G'], 0)
        self.assertEqual(observed[0]['C'], 1)

    def test_only_recorded_original_reads_can_contribute(self):
        self.assertFalse(consistent_locus_signatures([]))
        self.assertFalse(consistent_locus_signatures([(('x','y'), {})]))


if __name__ == '__main__':
    unittest.main()
