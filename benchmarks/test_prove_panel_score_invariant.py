"""Length bound is a proof only when best possible winner is retained."""
import unittest

from prove_panel_score_invariant import invariant_from_max_sequences


class PanelBoundTests(unittest.TestCase):
    def test_label_only_change_preserves_best_score(self):
        report=invariant_from_max_sequences(['A'*100,'ACGT'],
                                              ['ACGT','A'*100],87)
        self.assertTrue(report['unchanged_best_provable_by_length_bound'])
        self.assertEqual(report['baseline_max_sequences_lost_ignoring_labels'],0)

    def test_short_new_or_missing_partial_cannot_change_known_score(self):
        report=invariant_from_max_sequences(['C'*200,'G'*24],
                                              ['C'*200,'G'*22],188)
        self.assertTrue(report['unchanged_best_provable_by_length_bound'])
        self.assertEqual(report['longest_added_max_sequence'],22)
        self.assertEqual(report['longest_removed_max_sequence'],24)

    def test_missing_plausible_winner_refuses_proof(self):
        report=invariant_from_max_sequences(['A'*200,'C'*20],
                                              ['C'*20,'G'*30],180)
        self.assertFalse(report['unchanged_best_provable_by_length_bound'])

    def test_new_potential_winner_refuses_proof(self):
        report=invariant_from_max_sequences(['A'*200,'C'*20],
                                              ['A'*200,'G'*199],180)
        self.assertFalse(report['unchanged_best_provable_by_length_bound'])

    def test_invalid_data_and_missing_baseline_are_rejected(self):
        for originals,changed,score in (([],['ACT'],2),(['ACG'],[],3),
                                        (['ACG'],['ACG'],0),(['ACG'],['ACG'],True)):
            with self.assertRaises(ValueError):
                invariant_from_max_sequences(originals,changed,score)


if __name__=='__main__':
    unittest.main()
