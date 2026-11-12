"""Pairwise signed-power dominance is directed, complete and fail-closed."""
import unittest

from assembler_bench.psi_matrix import matrix


def record(index, a, b, c=None):
    data = {"A": {"status": "success", "score": a[0], "seconds": a[1]},
            "B": {"status": "success", "score": b[0], "seconds": b[1]}}
    if c is not None:
        data["C"] = {"status": "success", "score": c[0],
                     "seconds": c[1]}
    return {"id": str(index), "results": data}


class DirectedDominanceTests(unittest.TestCase):
    def test_each_direction_is_independently_verified(self):
        rows = [record(0, (8, 3), (5, 4), (6, 3.5)),
                record(1, (8, 3), (5, 4), (6, 3.5)),
                record(2, (8, 3), (5, 4), (6, 3.5))]
        report = matrix(rows, ["C", "A", "B"], expected=3, eligible=True)
        self.assertEqual(report["tools"], ["C", "A", "B"])
        for metric in ("alignment", "runtime", "joint"):
            grid = report["metrics"][metric]
            self.assertEqual(grid["A"]["B"]["status"], "dominates")
            self.assertEqual(grid["B"]["A"]["status"], "does-not-dominate")
            self.assertEqual(grid["A"]["A"]["status"], "self")
            self.assertEqual(grid["A"]["C"]["status"], "dominates")
            self.assertEqual(grid["C"]["B"]["status"], "dominates")
        self.assertEqual(report["metrics"]["alignment"]["A"]["B"]["proof"]
                         ["zeros_nonnegative"], [])

    def test_nonmonotone_psi_cannot_pass_from_average(self):
        # At r=0: +1/3, at high r: negative since the largest loss wins.
        rows = [record(1, (3, 1), (2, 2)),
                record(2, (3, 1), (2, 2)),
                record(3, (1, 1), (4, 2))]
        report = matrix(rows, ["A", "B"], expected=3, eligible=True)
        outcome = report["metrics"]["alignment"]["A"]["B"]
        self.assertEqual(outcome["status"], "does-not-dominate")
        self.assertEqual(outcome["proof"]["gains"], 2)
        self.assertEqual(outcome["proof"]["losses"], 1)
        self.assertGreater(outcome["proof"]["psi0"], 0)

    def test_missing_arms_and_ineligible_truth_are_incomplete(self):
        rows = [record(1, (5, 1), (4, 2)),
                record(2, (5, 1), (4, 2))]
        self.assertEqual(matrix(rows, ["A", "B"], expected=3, eligible=True)
                         ["metrics"]["alignment"]["A"]["B"]["status"],
                         "incomplete")
        self.assertEqual(matrix(rows, ["A", "B"], expected=2, eligible=False)
                         ["metrics"]["joint"]["A"]["B"]["status"],
                         "incomplete")
        rows[0]["results"]["B"]["status"] = "failed"
        self.assertEqual(matrix(rows, ["A", "B"], expected=2, eligible=True)
                         ["metrics"]["runtime"]["A"]["B"]["paired"], 1)

    def test_duplicate_identity_is_rejected(self):
        rows = [record(1, (5, 1), (4, 2))] * 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            matrix(rows, ["A", "B"], expected=2, eligible=True)

    def test_contradictory_axes_yield_non_dominant_joint(self):
        rows = [record(i, (5, 10), (4, 1)) for i in range(4)]
        result = matrix(rows, ["A", "B"], expected=4, eligible=True)
        a = result["metrics"]["joint"]["A"]["B"]
        self.assertEqual(a["status"], "does-not-dominate")
        self.assertEqual(result["metrics"]["alignment"]["A"]["B"]
                         ["status"], "dominates")
        self.assertEqual(result["metrics"]["runtime"]["A"]["B"]
                         ["status"], "does-not-dominate")


if __name__ == "__main__":
    unittest.main()
