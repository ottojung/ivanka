"""Fail-closed tests for the full-198 alignment and speed requirements."""
import math
import unittest
from copy import deepcopy

import milestone198


class SignedPowerTests(unittest.TestCase):
    def test_all_positive(self):
        result = milestone198.psi([2.0] * 198)
        self.assertEqual((result["psi0"], result["psi1"], result["psi2"]),
                         (1, 2, 4))
        self.assertEqual((result["gains"], result["losses"], result["ties"]),
                         (198, 0, 0))

    def test_zero_ties_contribute_nothing_even_for_power_zero(self):
        result = milestone198.psi([0] * 198)
        self.assertEqual([result[key] for key in ("psi0", "psi1", "psi2")],
                         [0, 0, 0])
        self.assertEqual(result["ties"], 198)

    def test_each_power_is_independent(self):
        result = milestone198.psi([1] * 100 + [-10] * 98)
        self.assertGreater(result["psi0"], 0)
        self.assertLess(result["psi1"], 0)
        self.assertLess(result["psi2"], 0)

    def test_psis_zero_on_balanced_positive_and_negative_deltas(self):
        result = milestone198.psi([3] * 99 + [-3] * 99)
        self.assertTrue(all(result[k] == 0 for k in ("psi0", "psi1", "psi2")))

    def test_reject_missing_nonfinite_or_boolean(self):
        for values in ([1] * 197, [1] * 197 + [math.nan],
                       [1] * 197 + [math.inf], [1] * 197 + [True]):
            with self.subTest(values=values[-1]):
                with self.assertRaises(ValueError):
                    milestone198.psi(values)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.names = ["S" + str(i) for i in range(198)]
        self.records = [
            {"sample": name, "status": "finished", "failed": False,
             "iva_baseline_reused": True, "total_seconds": 100.0,
             "iva": {"exit_code": 0, "image_id": "iva-id", "seconds": 60.,
                     "timing_origin": "micall_in_container_monotonic_v1",
                     "metrics": {"num_final_max_conseqs": 1}},
             "ivanka": {"exit_code": 0, "image_id": "ivanka-id",
                        "seconds": 50., "timing_origin": "micall_in_container_monotonic_v1",
                        "metrics": {"num_final_max_conseqs": 1}},
             "best_contig_acceptance": {
                 "method": "best_final_max_contig_local_alignment_over_reference_panel",
                 "reference_panel_sha256": milestone198.PANEL_SHA256,
                 "reference_count": 33, "iva_score": 200., "ivanka_score": 201.,
                 "pass": True}}
            for name in self.names]

    def score(self, records=None, names=None):
        return milestone198.qualify(
            self.records if records is None else records,
            self.names if names is None else names,
            "iva-id", "ivanka-id", 1800, milestone198.PANEL_SHA256)

    def test_full_positive_cohort_passes(self):
        report = self.score()
        self.assertTrue(report["milestone198_pass"])
        self.assertEqual(report["milestone198_valid_pairs"], 198)
        self.assertEqual(report["score_psi"]["psi2"], 1.0)
        self.assertEqual(report["time_psi"]["psi2"], 100.0)
        self.assertEqual(report["time_psi0"], 1)
        self.assertEqual(report["score_psi2"], 1)

    def test_every_sample_must_reach_ninety_percent(self):
        for bad_score in (179.999, None, float("nan")):
            with self.subTest(bad_score=bad_score):
                records = deepcopy(self.records)
                records[0]["best_contig_acceptance"]["ivanka_score"] = bad_score
                self.assertFalse(self.score(records)["milestone198_pass"])

    def test_ninety_percent_boundary_is_allowed(self):
        records = deepcopy(self.records)
        records[0]["best_contig_acceptance"]["ivanka_score"] = 180.
        for item in records[1:]:
            item["best_contig_acceptance"]["ivanka_score"] = 205.
        self.assertTrue(self.score(records)["milestone198_pass"])

    def test_unverified_control_or_runtime_fails_closed(self):
        for field, value in (("iva_baseline_reused", False),
                             ("total_seconds", 1801.0),
                             ("total_seconds", float("nan"))):
            records = deepcopy(self.records)
            records[0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.score(records)["milestone198_pass"])
        records = deepcopy(self.records)
        records[0]["iva"]["seconds"] = 0
        self.assertFalse(self.score(records)["milestone198_pass"])

    def test_missing_or_duplicate_records_fail(self):
        self.assertFalse(self.score(self.records[:-1])["milestone198_pass"])
        records = deepcopy(self.records)
        records[-1]["sample"] = records[0]["sample"]
        self.assertFalse(self.score(records)["milestone198_pass"])

    def test_psi_failure_does_not_pass_even_when_per_sample_floor_holds(self):
        records = deepcopy(self.records)
        for item in records:
            item["best_contig_acceptance"]["ivanka_score"] = 198.
        result = self.score(records)
        self.assertFalse(result["milestone198_pass"])
        self.assertEqual(result["score_psi"]["psi0"], -1)

    def test_legacy_or_mixed_timing_is_not_qualified(self):
        for arm in ("iva", "ivanka"):
            records = deepcopy(self.records)
            del records[0][arm]["timing_origin"]
            self.assertFalse(self.score(records)["milestone198_pass"])
            self.assertEqual(self.score(records)["milestone198_valid_pairs"],197)

    def test_runtime_sign_is_iva_minus_ivanka(self):
        records = deepcopy(self.records)
        for item in records:
            item["ivanka"]["seconds"] = 70.
        result = self.score(records)
        self.assertFalse(result["milestone198_pass"])
        self.assertEqual(result["time_psi"]["psi1"], -10)

    def test_panel_threshold_is_90_only_for_new_milestone(self):
        from unittest.mock import patch
        from reference_panel import panel_acceptance
        baseline = {"score": 100., "reference": "REF", "contig_index": 0,
                    "contig_count": 1, "contig_length": 100}
        candidate = dict(baseline, score=92.)
        panel = (("REF", "ACGT"),)
        with patch("reference_panel.final_max_sequences", return_value=["ACGT"]), \
             patch("reference_panel.best_panel_alignment",
                   side_effect=[baseline, candidate, baseline, candidate]):
            alpha = panel_acceptance("iva", "ivanka", panel)
            next_milestone = panel_acceptance("iva", "ivanka", panel, min_ratio=0.90)
        self.assertFalse(alpha["pass"])
        self.assertTrue(next_milestone["pass"])
        self.assertEqual(alpha["threshold"], 95.)
        self.assertEqual(next_milestone["threshold"], 90.)

    def test_optimized_python_cannot_skip_scientific_guards(self):
        import os
        from pathlib import Path
        import subprocess
        import sys

        code = """
from copy import deepcopy
from test_milestone198 import QualificationTests
test = QualificationTests()
test.setUp()
cases = [
    (("failed",), True),
    (("status",), "error"),
    (("iva_baseline_reused",), False),
    (("ivanka", "image_id"), "wrong"),
    (("best_contig_acceptance", "reference_count"), 32),
    (("best_contig_acceptance", "pass"), False),
    (("total_seconds",), 1801.0),
    (("iva", "seconds"), 0.0),
]
for path, value in cases:
    records = deepcopy(test.records)
    item = records[0]
    for part in path[:-1]:
        item = item[part]
    item[path[-1]] = value
    if test.score(records)["milestone198_pass"]:
        raise RuntimeError("Optimized Python accepted invalid evidence: " + str(path))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent)
        result = subprocess.run(
            [sys.executable, "-O", "-c", code],
            env=env, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_disallow_panel_or_image_mismatch(self):
        self.assertFalse(milestone198.qualify(
            self.records, self.names, "iva-id", "ivanka-id", 1800, "wrong")["milestone198_pass"])
        records = deepcopy(self.records)
        records[0]["ivanka"]["image_id"] = "different"
        self.assertFalse(self.score(records)["milestone198_pass"])


if __name__ == "__main__":
    unittest.main()


class DiagnosticScoreFloorTests(unittest.TestCase):
    def test_explicit_90_percent_subset_diagnostic(self):
        from types import SimpleNamespace
        from podman_full_micall import alignment_score_floor
        self.assertEqual(alignment_score_floor(SimpleNamespace()), 0.95)
        self.assertEqual(alignment_score_floor(SimpleNamespace(diagnostic_90_floor=True)), 0.90)
        self.assertEqual(alignment_score_floor(SimpleNamespace(qualify_198=True)), 0.90)

    def test_diagnostic_flag_cannot_change_alpha_default(self):
        from types import SimpleNamespace
        from podman_full_micall import alignment_score_floor
        self.assertEqual(alignment_score_floor(SimpleNamespace(qualify=True)), 0.95)
