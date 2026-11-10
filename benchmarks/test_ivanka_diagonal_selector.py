import random
import unittest

from ivanka_diagonal_selector import build_position_index, diagonal_support, rank_diagonal, preserve_original_order
from ivanka_reference_selector import COMPLEMENT


class CoherentKmerRankingTests(unittest.TestCase):
    def test_prefers_colinear_reference_support_over_disjoint_matches(self):
        rng = random.Random(51)
        reference = "".join(rng.choices("ACGT", k=2500))
        index = build_position_index([("ref", reference)], k=21)
        coherent = reference[500:680]
        # More reference-matching bases overall, but from unrelated
        # positions whose diagonals do not agree.
        scattered = "".join(reference[i:i+40] for i in
                            (100, 1700, 400, 1900, 1100, 2200, 900, 2100))
        self.assertGreater(len(scattered), len(coherent))
        ranking = rank_diagonal([(">scatter", scattered), (">coherent", coherent)], index)
        self.assertEqual(ranking[0][0], 1)
        self.assertGreater(ranking[0][2], ranking[1][2])

    def test_native_emitter_order_preserved_after_quality_selection(self):
        entries = [(">a", "A"), (">b", "BB"), (">c", "CCC")]
        ranked = [(2, 3, 20), (0, 1, 10), (1, 2, 5)]
        selected, scores = preserve_original_order(entries, ranked, 2)
        self.assertEqual(selected, [entries[0], entries[2]])
        self.assertEqual(scores, [10, 20])

        reference = "ACGTTGCATAGGCTACCGTATGGTACCTGAACTCGTATCCGATGCTGGATCA"
        index = build_position_index([("ref", reference)], k=11)
        reverse = reference.translate(COMPLEMENT)[::-1]
        self.assertEqual(diagonal_support(reference, index, 11),
                         diagonal_support(reverse, index, 11))

    def test_all_unmatched_fallback_is_longer_then_stable(self):
        index = build_position_index([("ref", "ACGT" * 20)], k=21)
        result = rank_diagonal([(">short", "N" * 40), (">first", "N" * 80),
                                (">second", "N" * 80)], index)
        self.assertEqual([v[0] for v in result], [1, 2, 0])

    def test_reference_indices_avoid_ambiguous_kmers(self):
        idx = build_position_index([("ref","NNNNACGTACGTACGTNN")], k=5)
        self.assertFalse(any("N" in k for k in idx))
