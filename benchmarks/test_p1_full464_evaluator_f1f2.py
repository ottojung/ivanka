"""Fail-closed evaluator probes for controller defects F1 and F2.

These tests exercise ``evaluate()`` in-process with synthetic rows only. They
never start a container, run a cohort case, or read the live pinned results.
F1: a success-status rival with an empty ``per_truth`` must be counted as
    failed/incomplete and make ``evaluate()`` fail closed, not vanish from both
    the available and failed rosters while still feeding all-r Psi.
F2: an available rival with a valid ``per_truth`` but no ``score`` must produce
    a reported fail-closed error, not an unhandled ``KeyError`` that aborts the
    worker before it can write an evaluation report.
"""
import unittest

from benchmarks.expanded.p1_full464_controller import evaluate

RIVALS = ("iva", "abyss", "haploflow", "megahit", "spades", "velvet")
SCALE = 10000


def arm(fraction, seconds, *, per_truth=True):
    """A self-consistent arm: combined score matches the per-truth panel."""
    raw = fraction * 1000
    result = {
        "status": "success",
        "score": SCALE * fraction,
        "seconds": seconds,
        "sha256": "a" * 64,
        "score_origin": "micall_final_max_abundant_truths_balanced_v2",
        "timing_origin": "micall_in_container_monotonic_v1",
        "per_truth": ({"truth_0": {
            "score": raw, "length": 1000, "fraction": raw / 1000,
            "truth_sha256": "b" * 64, "nominal_abundance": 1.0,
        }} if per_truth else {}),
    }
    return result


def consistent_rows():
    rows = []
    for index in range(464):
        results = {"ivanka": arm(0.96, 10)}
        for name in RIVALS:
            results[name] = arm(0.95, 20)
        rows.append({"id": f"clonal-s{index:03d}",
                     "family": "clonal", "results": results})
    return rows


class EvaluatorFailClosedTests(unittest.TestCase):
    def test_f1_success_empty_per_truth_is_failed_not_silently_dropped(self):
        """Reviewer scenario H1: full 464 plus velvet=success/per_truth={}."""
        rows = consistent_rows()
        for row in rows:
            row["results"]["velvet"] = arm(0.95, 20, per_truth=False)
        report = evaluate(rows)

        self.assertFalse(report["pass"],
                         "incomplete rival evidence must fail closed")
        self.assertGreater(len(report["errors"]), 0,
                           "incomplete rival must produce reported errors")
        self.assertEqual(report["qualification_claim"], "NONE")
        sample = report["per_case"][0]
        self.assertIn("velvet", sample["failed_rivals"],
                      "incomplete rival must be counted in failure accounting")
        self.assertNotIn("velvet", sample["available_rivals"],
                         "empty per_truth rival is not available evidence")
        self.assertNotEqual(report["all_r_psi"]["velvet"]["status"],
                            "positive_all_r",
                            "incomplete rival must not earn all-r Psi")
        self.assertTrue(any("velvet" in error for error in report["errors"]),
                        "the failing rival must be named in the errors")

    def test_f2_available_rival_missing_score_fails_closed_without_keyerror(self):
        """Reviewer scenario H2: available spades with valid per_truth, no score."""
        rows = consistent_rows()
        del rows[0]["results"]["spades"]["score"]

        try:
            report = evaluate(rows)
        except KeyError as exc:
            self.fail(f"evaluate() must fail closed, not raise KeyError: {exc}")

        self.assertFalse(report["pass"])
        self.assertTrue(any("spades" in error and "score" in error
                            for error in report["errors"]),
                        "missing score must be a reported error")
        self.assertEqual(report["qualification_claim"], "NONE")


if __name__ == "__main__":
    unittest.main()
