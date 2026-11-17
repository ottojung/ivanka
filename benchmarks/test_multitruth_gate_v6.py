"""Qualification cannot hide a missed >=15% truth behind another truth."""
import unittest

from expanded.gate import eligible_truth
from expanded.gate_multitruth import check_sample


def outcome(first, second):
    score = 5000 * (first + second)
    return {
        "score": score,
        "per_truth": {
            "truth_0": {"score": first * 9646, "length": 9646,
                        "fraction": first},
            "truth_1": {"score": second * 550, "length": 550,
                        "fraction": second},
        },
    }


class MultitruthGateV6(unittest.TestCase):
    def test_each_required_truth_has_a_separate_ninety_percent_floor(self):
        rivals = {name: outcome(0.90, 0.90) for name in ("iva", "velvet")}
        passing = {"ivanka": outcome(0.87, 0.87), **rivals}
        self.assertEqual(check_sample("s1", passing, rivals, 0.90), [])
        missing = {"ivanka": outcome(1.0, 0.65), **rivals}
        self.assertGreater(missing["ivanka"]["score"], 0.90 * 9000)
        self.assertIn("s1:ivanka_below_90pct_for_truth_1",
                      check_sample("s1", missing, rivals, 0.90))

    def test_missing_or_inconsistent_truth_metrics_fail_closed(self):
        rivals = {"iva": outcome(0.9, 0.9)}
        absent = {"ivanka": {"score": 9000}, **rivals}
        self.assertIn("s2:ivanka:missing_per_truth",
                      check_sample("s2", absent, rivals, 0.9))
        mismatch = {"ivanka": outcome(0.9, 0.9), **rivals}
        mismatch["ivanka"]["per_truth"].pop("truth_1")
        self.assertIn("s2:iva:inconsistent_truth_panel",
                      check_sample("s2", mismatch, rivals, 0.9))

    def test_bad_combined_score_or_fabricated_raw_alignment_fails(self):
        rivals = {"iva": outcome(0.9, 0.9)}
        tampered = {"ivanka": outcome(0.9, 0.9), **rivals}
        tampered["ivanka"]["score"] += 1
        self.assertIn("s3:ivanka:incorrect_combined_score",
                      check_sample("s3", tampered, rivals, 0.9))
        tampered["ivanka"]["per_truth"]["truth_1"]["score"] = 600
        self.assertIn("s3:ivanka:invalid_truth_alignment",
                      check_sample("s3", tampered, rivals, 0.9))

    def test_end_to_end_gate_cannot_hide_missed_fifteen_percent_v3_region(self):
        from expanded.gate import summarize_gate
        from expanded.adapters import ASSEMBLERS
        proof = {"schema": "ivanka.mixed_viral_truth_validation.v4",
                 "valid": True, "split": "development", "seed_start": 0,
                 "normal_pairs": 10000, "min_abundance": .15,
                 "scoring_method": "balanced_abundant_truths_v1",
                 "mixed_source_sha256": "a"*64,
                 "cohort_sha256": "b"*64,
                 "verification_sha256": "c"*64}
        def arm(tool, cohort):
            if cohort == "real":
                return {"score": 120 if tool == "ivanka" else 100,
                        "score_origin": "micall_final_max_reference_panel_v1",
                        "seconds": 1 if tool == "ivanka" else 2,
                        "timing_origin": "micall_in_container_monotonic_v1",
                        "sha256": "a"*64, "status": "success"}
            row = outcome(1.0, .65) if tool == "ivanka" else outcome(.9, .9)
            return {**row, "status": "success", "sha256": "a"*64,
                    "seconds": 1 if tool == "ivanka" else 2,
                    "score_origin": "micall_final_max_abundant_truths_balanced_v2",
                    "timing_origin": "micall_in_container_monotonic_v1"}
        def case(cohort):
            return {"id": "real-a" if cohort == "real" else "hcv_v3_15pct-s000",
                    "family": None if cohort == "real" else "hcv_v3_15pct",
                    "cohort": cohort, "input_sha256": "f"*64,
                    **({"truth_validation": proof} if cohort == "synthetic" else {}),
                    "results": {tool: arm(tool, cohort) for tool in ASSEMBLERS}}
        result = summarize_gate([case("real"), case("synthetic")],
                                real_count=1, synthetic_seeds=1,
                                families=("hcv_v3_15pct",))
        self.assertFalse(result["pass"])
        self.assertIn("hcv_v3_15pct-s000:ivanka_below_90pct_for_truth_1",
                      result["errors"])
        self.assertNotIn("hcv_v3_15pct-s000:ivanka_below_90pct_best_competitor",
                         result["errors"])

    def test_v4_truth_proof_requires_correct_cutoff_and_split(self):
        proof = {"schema": "ivanka.mixed_viral_truth_validation.v4",
                 "valid": True, "split": "development", "seed_start": 0,
                 "normal_pairs": 10000, "min_abundance": .15,
                 "scoring_method": "balanced_abundant_truths_v1",
                 "mixed_source_sha256": "a"*64,
                 "cohort_sha256": "b"*64,
                 "verification_sha256": "c"*64}
        self.assertTrue(eligible_truth({"truth_validation": proof}))
        proof["min_abundance"] = .10
        self.assertFalse(eligible_truth({"truth_validation": proof}))
        proof["min_abundance"] = .15
        proof["split"] = "validation"
        self.assertFalse(eligible_truth({"truth_validation": proof}))


if __name__ == "__main__":
    unittest.main()
