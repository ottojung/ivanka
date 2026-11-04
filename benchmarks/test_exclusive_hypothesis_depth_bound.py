"""Negative controls for necessary exclusive hypothesis support bounds."""
import unittest

from exclusive_hypothesis_depth_bound import exclusive_support_bound


def sample(counts, names=("A", "B", "C", "D")):
    return {"reference_names": list(names),
            "pooled_deduplicated": {"per_position": list(counts)}}


class AllocationBoundTests(unittest.TestCase):
    def test_four_contigs_cannot_each_receive_100_from_120(self):
        v = exclusive_support_bound(sample((383, 120, 490)))
        self.assertFalse(
            v["all_hypotheses_possible_under_exclusive_assignment_necessary_test"])
        self.assertEqual(v["minimum_pooled_allele_matching_pair_ids"], 120)
        self.assertEqual(v["minimum_missing_pair_site_votes_to_cover_all"], 280)
        self.assertEqual(v["maximum_hypotheses_at_full_depth_upper_bound"], 1)

    def test_s98_206_max_two_of_four_does_not_prove_two_feasible(self):
        v = exclusive_support_bound(sample((266, 206, 308)))
        self.assertEqual(v["maximum_hypotheses_at_full_depth_upper_bound"], 2)
        self.assertEqual(v["minimum_missing_pair_site_votes_to_cover_all"], 194)
        self.assertFalse(
            v["all_hypotheses_possible_under_exclusive_assignment_necessary_test"])

    def test_passing_necessary_bound_is_not_sufficient(self):
        v = exclusive_support_bound(sample((400, 550)))
        self.assertTrue(
            v["all_hypotheses_possible_under_exclusive_assignment_necessary_test"])
        self.assertIn("Passing does not prove", v["interpretation"])

    def test_short_or_invalid_inputs_fail_closed(self):
        for value in (0, -1, 1.2, True):
            with self.assertRaises(ValueError):
                exclusive_support_bound(sample((10, 20)), value)
        for report in (sample((), ("A", "B")), sample((10,), ("A",)),
                       sample((1, 2), ("A", "A")),
                       sample((1, 2), ("A", [])),
                       sample((1, -1)), sample((True, 3)),
                       sample((1.2, 3))):
            with self.assertRaises(ValueError):
                exclusive_support_bound(report)


if __name__ == "__main__":
    unittest.main()
