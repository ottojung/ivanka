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

    def test_diagnostic_subjects_support_both_explicit_directions(self):
        rows = [record(i, (4, 2), (3, 4)) for i in range(3)]
        for row in rows:
            row["results"]["A"]["diagnostics"] = {
                "clipped_read_fraction": .1, "primary_mapped_fraction": .8}
            row["results"]["B"]["diagnostics"] = {
                "clipped_read_fraction": .3, "primary_mapped_fraction": .5}
        result = matrix(rows, ["A","B"], expected=3, eligible=True,
                        diagnostic_keys=("clipped_read_fraction",
                                         "primary_mapped_fraction"))
        grid=result["metrics"]
        low=grid["diagnostic:clipped_read_fraction:lower"]
        high=grid["diagnostic:primary_mapped_fraction:higher"]
        self.assertEqual(low["A"]["B"]["status"], "dominates")
        self.assertEqual(low["B"]["A"]["status"], "does-not-dominate")
        self.assertEqual(high["A"]["B"]["status"], "dominates")
        self.assertEqual(grid["diagnostic:clipped_read_fraction:higher"][
            "A"]["B"]["status"], "does-not-dominate")

    def test_diagnostic_no_sample_pairs_means_no_fabricated_proofs(self):
        rows = [record(i,(4,2),(3,4)) for i in range(3)]
        result=matrix(rows, ["A","B"], expected=3, eligible=True,
                      diagnostic_keys=("soft_clipped_bases",))
        self.assertNotIn("diagnostic:soft_clipped_bases:higher",
                         result["metrics"])
        rows[0]["results"]["A"]["diagnostics"]={"soft_clipped_bases":1}
        rows[0]["results"]["B"]["diagnostics"]={"soft_clipped_bases":2}
        result=matrix(rows, ["A","B"], expected=3, eligible=True,
                      diagnostic_keys=("soft_clipped_bases",))
        entry=result["metrics"]["diagnostic:soft_clipped_bases:lower"][
            "A"]["B"]
        self.assertEqual(entry["status"], "incomplete")
        self.assertEqual(entry["paired"], 1)

    def test_partial_pair_observations_never_claim_cohort_dominance(self):
        rows = [record(0, (8, 3), (5, 4), (6, 5)),
                record(1, (8, 3), (5, 4), (6, 5))]
        rows[1]["results"]["C"]["status"] = "failed"
        result = matrix(rows, ["A", "B", "C"], expected=400, eligible=False)
        ab=result["metrics"]["alignment"]["A"]["B"]
        ac=result["metrics"]["alignment"]["A"]["C"]
        self.assertEqual(ab["status"], "incomplete")
        self.assertIsNone(ab["proof"])
        self.assertEqual(ab["paired"],2)
        self.assertEqual(ab["observed"]["gains"],2)
        self.assertEqual(ab["observed"]["losses"],0)
        self.assertEqual(ac["paired"],1)
        self.assertEqual(ac["observed"]["mean_delta"],2)
        self.assertIsNone(ac["proof"])

    def test_incomplete_subset_is_independently_proven_for_all_real_exponents(self):
        # Observed A>B twice, but one large regression at high r:
        # win counts and average are NOT signed-power dominance.
        rows = [record(1,(102,2),(100,5)),
                record(2,(102,2),(100,5)),
                record(3,(80,2),(100,5))]
        grid = matrix(rows,["A","B"],expected=400,eligible=False)["metrics"]
        item = grid["alignment"]["A"]["B"]
        self.assertEqual(item["status"],"incomplete")
        self.assertIsNone(item["proof"])
        self.assertEqual(item["subset"]["status"],"does-not-dominate")
        self.assertFalse(item["subset"]["proof"]["positive_all_nonnegative"])
        self.assertEqual(item["paired"],3)
        self.assertEqual(item["observed"]["gains"],2)
        self.assertEqual(item["observed"]["losses"],1)
        self.assertEqual(grid["runtime"]["A"]["B"]["subset"]["status"],
                         "dominates")
        self.assertEqual(grid["alignment"]["B"]["A"]["subset"]["status"],
                         "does-not-dominate")

    def test_observed_dominance_is_preserved_when_other_arm_fails(self):
        rows = [record(0,(8,2),(4,5),(4,5)),
                record(1,(8,2),(4,5),(4,5)),
                record(2,(8,2),(4,5),(4,5))]
        rows[2]["results"]["C"]["status"]="failed"
        grid=matrix(rows,["A","B","C"],expected=400,eligible=False)["metrics"]
        ab=grid["alignment"]["A"]["B"]
        ac=grid["alignment"]["A"]["C"]
        self.assertEqual(ab["subset"]["status"],"dominates")
        self.assertEqual(ab["paired"],3)
        self.assertEqual(ac["subset"]["status"],"dominates")
        self.assertEqual(ac["paired"],2)
        self.assertIsNone(ac["proof"])
        self.assertEqual(ac["status"],"incomplete")

    def test_ties_and_unobserved_pairs_never_produce_positive_subset(self):
        rows=[record(i,(4,2),(4,2)) for i in range(2)]
        grid=matrix(rows,["A","B"],expected=400,eligible=False)["metrics"]
        entry=grid["alignment"]["A"]["B"]
        self.assertEqual(entry["subset"]["status"],"does-not-dominate")
        self.assertEqual(entry["subset"]["proof"]["psi0"],0)
        self.assertEqual(entry["subset"]["proof"]["zeros_nonnegative"],"R>=0")
        rows[0]["results"]["A"]["status"]="failed"
        rows[1]["results"]["B"]["status"]="failed"
        entry=matrix(rows,["A","B"],expected=400,eligible=False)[
            "metrics"]["alignment"]["A"]["B"]
        self.assertEqual(entry["paired"],0)
        self.assertEqual(entry["subset"]["status"],"no-data")
        self.assertIsNone(entry["subset"]["proof"])

    def test_independent_pairwise_subset_certificates_cannot_be_promoted(self):
        rows=[record(i,(6,1),(4,2)) for i in range(3)]
        grid=matrix(rows,["A","B"],expected=400,eligible=False)["metrics"]
        for metric in ("alignment","runtime"):
            entry=grid[metric]["A"]["B"]
            self.assertEqual(entry["status"],"incomplete")
            self.assertEqual(entry["subset"]["status"],"dominates")
            self.assertIsNone(entry["proof"])
            self.assertEqual(entry["subset"]["proof"]["psi0"],1)
        joint=grid["joint"]["A"]["B"]
        self.assertEqual(joint["status"],"incomplete")
        self.assertEqual(joint["subset"]["alignment"]["status"],"dominates")
        self.assertEqual(joint["subset"]["runtime"]["status"],"dominates")

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
