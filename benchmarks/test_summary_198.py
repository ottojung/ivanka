"""The CLI distinguishes frozen 198 qualification from historical 18-sample alpha."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import summarize
from milestone198 import IVA_IMAGE_SHA256, MANIFEST_SHA256, PANEL_SHA256

GOOD_PSI = {
    "positive_all_nonnegative": True,
    "zeros_nonnegative": [],
    "psi_at_positive_infinity": "+inf",
    "psi0": 0.04, "psi1": 0.8, "psi2": 25.0,
}


def valid198():
    return {
        "invocation": "1793748303-test", "mode": "ivanka",
        "qualification_requested": True, "qualification198_requested": True,
        "all_projects": True, "allow_missing_baseline": False,
        "parallel_arms": False, "resumed_diagnostic_only": False,
        "stopped_early_after_irreversible_failure": False,
        "resumed_completed_samples": 0,
        "manifest_sample_count": 198, "selected_samples": 198,
        "finished_samples": 198, "accepted_samples": 198,
        "milestone198_valid_pairs": 198, "milestone198_expected": 198,
        "failed_samples": [], "milestone198_errors": [],
        "manifest_sha256": MANIFEST_SHA256,
        "reference_panel_sha256": PANEL_SHA256, "reference_panel_count": 33,
        "iva_baseline_image_id": IVA_IMAGE_SHA256,
        "images": {"ivanka": "a" * 64},
        "hxb2_sha256": "b" * 64,
        "project_reference_catalog_sha256": "c" * 64,
        "milestone198_min_alignment_ratio": 0.9,
        "sample_limit_seconds": 1800,
        "max_container_wall_seconds": 1100.0,
        "score_psi": dict(GOOD_PSI), "time_psi": dict(GOOD_PSI),
        "milestone198_pass": True,
    }


class Summary198Tests(unittest.TestCase):
    def test_valid_milestone_has_correct_count_and_wall_clock_label(self):
        report = summarize.evaluate(valid198())
        self.assertTrue(report["pass"], report["reasons"])
        self.assertEqual(report["required_samples"], 198)
        self.assertEqual(report["time_label"], "max_container_wall_seconds")

    def test_partial_resumed_or_unproven_summary_never_passes(self):
        variants = [
            {"qualification198_requested": False},
            {"qualification_requested": False},
            {"all_projects": False},
            {"mode": "both"},
            {"resumed_diagnostic_only": True},
            {"resumed_completed_samples": 1},
            {"selected_samples": 197},
            {"finished_samples": 197},
            {"accepted_samples": 197},
            {"milestone198_valid_pairs": 197},
            {"failed_samples": ["S48"]},
            {"milestone198_errors": ["runner_rejected"]},
            {"stopped_early_after_irreversible_failure": True},
            {"manifest_sha256": "a" * 64},
            {"reference_panel_sha256": "a" * 64},
            {"reference_panel_count": 32},
            {"iva_baseline_image_id": "a" * 64},
            {"images": {"ivanka": "not-an-image"}},
            {"milestone198_min_alignment_ratio": 0.8},
            {"sample_limit_seconds": 1801},
            {"max_container_wall_seconds": 1801},
            {"max_container_wall_seconds": 10**1000},
            {"score_psi": dict(GOOD_PSI, psi0=10**1000)},
            {"milestone198_pass": False},
            {"score_psi": dict(GOOD_PSI, positive_all_nonnegative=False)},
            {"score_psi": dict(GOOD_PSI, psi0=0)},
            {"time_psi": dict(GOOD_PSI, zeros_nonnegative=[1.5])},
            {"time_psi": dict(GOOD_PSI, psi_at_positive_infinity="-inf")},
            {"time_psi": None},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertFalse(summarize.evaluate(valid198() | variant)["pass"])

    def test_cli_works_and_fails_closed_on_nonpass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary-1793748303-test.json"
            path.write_text(json.dumps(valid198()))
            cli = Path(__file__).with_name("summarize.py")
            args = [sys.executable, str(cli), "--results", str(path),
                    "--invocation", "1793748303-test"]
            ok = subprocess.run(args, text=True, capture_output=True, check=False)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("198/198 accepted", ok.stdout)
            self.assertIn("max_container_wall_seconds=1100", ok.stdout)
            path.write_text(json.dumps(valid198() | {"milestone198_pass": False}))
            bad = subprocess.run(args, text=True, capture_output=True, check=False)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("NOT PASS", bad.stdout)


if __name__ == "__main__":
    unittest.main()
