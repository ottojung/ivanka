"""Hermetic tests for strict unique paired anchor evidence."""
import gzip
from pathlib import Path
import random
import tempfile
import unittest

import p1_pair_spanning as span


class PairSpanningTests(unittest.TestCase):
    def setUp(self):
        rng = random.Random(381)
        self.truth = "".join(rng.choice("ACGT") for _ in range(1000))
        self.index = span.unique_index(self.truth)

    def test_unique_placement_both_strands(self):
        read = self.truth[20:170]
        self.assertEqual(span.placement(read, self.index), (20, 1, 20, 139))
        self.assertEqual(span.placement(span.reverse(read), self.index),
                         (20, -1, 20, 139))
        self.assertIsNone(span.placement(read[:31], self.index))
        self.assertIsNone(span.placement("N"*150, self.index))

    def test_inward_spanning_and_reversed_order(self):
        first = span.placement(self.truth[20:170], self.index)
        second = span.placement(span.reverse(self.truth[720:870]), self.index)
        gaps = [(200, 400), (450, 650), (750, 950)]
        self.assertEqual(span.bridges(first, second, gaps), (0, 1))
        self.assertEqual(span.bridges(second, first, gaps), (0, 1))
        self.assertEqual(span.bridges(first, span.placement(self.truth[720:870],
                                                          self.index), gaps), ())
        self.assertEqual(span.bridges(None, second, gaps), ())

    def test_repeat_and_disagreeing_anchors_refused(self):
        repeat = self.truth[:150]
        index = span.unique_index(repeat+self.truth[150:500]+repeat)
        self.assertIsNone(span.placement(repeat, index))
        self.assertIsNone(span.placement(self.truth[:75]+self.truth[600:675],
                                        self.index))

    def test_gap_boundaries(self):
        self.assertEqual(list(span.absent_runs([False]*150+[True]+[False]*149)),
                         [(0,150)])
        self.assertEqual(list(span.absent_runs([True]+[False]*151)), [(1,152)])

    def test_mate_identity_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp)/f"r{i}.fq.gz" for i in (1,2)]
            for i,p in enumerate(paths,1):
                with gzip.open(p,"wt") as f:
                    f.write(f"@name{i} {i}:N:0:1\nACGT\n+\nIIII\n")
            with self.assertRaisesRegex(ValueError,"mismatched mate"):
                list(span.paired(paths))
            with gzip.open(paths[1],"wt") as f:
                f.write("@name1 2:N:0:1\nACGT\n+\nIIII\n")
            self.assertEqual(list(span.paired(paths)), [("ACGT","ACGT")])


if __name__ == "__main__":
    unittest.main()
