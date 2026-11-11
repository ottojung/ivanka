"""Non-reference scoring contracts for selection of dominant read support."""

import random
import unittest

from ivanka_read_support_selector import rank_by_pair_weighted_breadth


class ReadSupportRankingContract(unittest.TestCase):
    def test_stronger_fragment_support_increases_rank(self):
        entries = [(">x", "A"*500), (">y", "C"*500)]
        self.assertEqual(rank_by_pair_weighted_breadth(entries, [200,200], [20,30]), [1,0])

    def test_wider_supported_span_increases_rank(self):
        entries = [(">x", "A"*500), (">y", "C"*500)]
        self.assertEqual(rank_by_pair_weighted_breadth(entries, [200,230], [30,30]), [1,0])

    def test_offtarget_length_without_support_does_not_win(self):
        entries = [(">long", "A"*5000), (">supported", "C"*600)]
        self.assertEqual(rank_by_pair_weighted_breadth(entries, [0,500], [1000,20]), [1,0])

    def test_ties_preserve_source_order(self):
        entries = [(">one", "A"*500), (">two", "C"*500)]
        self.assertEqual(rank_by_pair_weighted_breadth(entries, [200]*2, [30]*2), [0,1])

    def test_does_not_modify_input_metrics(self):
        entries = [(">x","A"*500),(">y","C"*700)]
        coverage, pairs = [300,100], [55,80]
        rank_by_pair_weighted_breadth(entries, coverage, pairs)
        self.assertEqual((coverage,pairs), ([300,100],[55,80]))

    def test_random_metrics_follow_independent_oracle(self):
        rng = random.Random(14172)
        for _ in range(100):
            n = rng.randint(2, 7)
            lengths = [rng.randint(60, 1200) for _ in range(n)]
            coverage = [rng.randint(0, length-30) for length in lengths]
            pairs = [rng.randint(0, 1000) for _ in lengths]
            entries = [(str(i), "A"*length) for i,length in enumerate(lengths)]
            actual = rank_by_pair_weighted_breadth(entries, coverage, pairs)
            def score(i, coverage=coverage, pairs=pairs, lengths=lengths):
                return coverage[i]**2*pairs[i]/(lengths[i]-30)
            expected = sorted(range(n), key=lambda i: (-score(i),-coverage[i]*pairs[i],
                                                        -coverage[i],-pairs[i],-lengths[i],i))
            self.assertEqual(actual, expected)
