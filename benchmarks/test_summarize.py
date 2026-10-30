"""Regression tests for IVA-eligible eighteen-input, per-sample twenty-minute full-alpha report summaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "alpha_summarize", Path(__file__).parent / "summarize.py")
summarize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarize)


def valid():
    sha = "a" * 64
    return {
        "invocation": "1793307581-test",
        "mode": "both",
        "qualification_requested": True,
        "allow_missing_baseline": False,
        "manifest_sample_count": 18,
        "selected_samples": 18,
        "finished_samples": 18,
        "accepted_samples": 18,
        "failed_samples": [],
        "max_sample_seconds": 1199.0,
        "sample_limit_seconds": 1200,
        "manifest_sha256": sha,
        "hxb2_sha256": sha,
        "project_reference_catalog_sha256": sha,
        "reference_panel_sha256": sha,
        "reference_panel_count": 33,
        "source_manifest_sha256": sha,
        "iva_eligibility_evidence_sha256": sha,
        "iva_ineligible_excluded": 2,
        "images": {"iva": sha, "ivanka": sha},
        "full_alpha_pass": True,
    }


class SummarizeTests(unittest.TestCase):
    def test_complete_eligible_eighteen_within_each_sample_limit_passes(self):
        self.assertTrue(summarize.evaluate(valid())["pass"])

    def test_bad_conditions_fail_closed(self):
        changes = [
            {"mode": "ivanka"},
            {"qualification_requested": False},
            {"allow_missing_baseline": True},
            {"accepted_samples": 17},
            {"selected_samples": 17},
            {"finished_samples": 17},
            {"manifest_sample_count": 7},
            {"failed_samples": ["private-sample"]},
            {"max_sample_seconds": 1201},
            {"sample_limit_seconds": 1201},
            {"max_sample_seconds": 1199, "sample_limit_seconds": 1180},
            {"full_alpha_pass": False},
            {"images": {"iva": "a"*64}},
            {"manifest_sha256": "bogus"},
            {"project_reference_catalog_sha256": None},
            {"iva_ineligible_excluded": 0},
            {"source_manifest_sha256": None},
            {"iva_eligibility_evidence_sha256": None},
            {"manifest_sample_count": 20, "selected_samples": 20,
             "finished_samples": 20, "accepted_samples": 20},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(summarize.evaluate(valid() | change)["pass"])

    def test_duplicate_invocations_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for i in (1, 2):
                (p / f"summary-{i}.json").write_text(json.dumps(valid()))
            with self.assertRaisesRegex(ValueError, "duplicate invocation"):
                summarize.load_reports(p)

    def test_invalid_and_missing_summary_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with self.assertRaisesRegex(ValueError, "no summary"):
                summarize.load_reports(p)
            (p / "summary-a.json").write_text("{invalid")
            with self.assertRaisesRegex(ValueError, "invalid summary JSON"):
                summarize.load_reports(p)


if __name__ == "__main__":
    unittest.main()
