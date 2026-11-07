"""Direct pair-sequence evidence cannot be inflated by missing observations."""
import unittest

from original_pair_locus_links import count_direct_links


class OriginalPairLocusLinksTests(unittest.TestCase):
    def test_partial_repeated_signature_never_counts_as_distinct_pair(self):
        records = [
            (("R1", "R2"), {1: "A", 2: "G"}),
            (("R1", "R2"), {1: "A"}),
            (("R3", "R4"), {1: "C", 2: "T"}),
            (("R3", "R4"), {1: "C", 2: "T"}),
        ]
        count, distinct = count_direct_links(records, {1, 2})
        self.assertEqual(count[1, 2]["A", "G"], 1)
        self.assertEqual(distinct[1, 2]["A", "G"], 0)
        self.assertEqual(count[1, 2]["C", "T"], 2)
        self.assertEqual(distinct[1, 2]["C", "T"], 1)

    def test_differently_called_identical_pair_sequences_are_excluded(self):
        records = [
            (("X", "Y"), {1: "A", 2: "G"}),
            (("X", "Y"), {1: "C", 2: "T"}),
        ]
        count, distinct = count_direct_links(records, {1, 2})
        self.assertEqual(sum(count[1, 2].values()), 2)
        self.assertEqual(sum(distinct[1, 2].values()), 0)

    def test_two_edges_never_create_missing_transitive_third_edge(self):
        records = [
            (("X1", "Y1"), {1: "A", 2: "C"}),
            (("X2", "Y2"), {2: "C", 3: "G"}),
        ]
        count, distinct = count_direct_links(records, {1, 2, 3})
        self.assertEqual(count[1, 2]["A", "C"], 1)
        self.assertEqual(count[2, 3]["C", "G"], 1)
        self.assertNotIn((1, 3), count)
        self.assertNotIn((1, 3), distinct)

    def test_unqualified_groups_are_not_eligible_for_evidence(self):
        records = [(("X1", "Y1"), {1: "A", 2: "C", 3: "G"})]
        count, distinct = count_direct_links(records, {1, 3})
        self.assertEqual(set(count), {(1, 3)})
        self.assertEqual(distinct[1, 3]["A", "G"], 1)


if __name__ == "__main__":
    unittest.main()
