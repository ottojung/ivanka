"""Regression tests for twenty-input, forty-minute full-alpha report summaries."""
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
        "manifest_sample_count": 20,
        "selected_samples": 20,
        "finished_samples": 20,
        "accepted_samples": 20,
        "failed_samples": [],
        "global_seconds": 2399.0,
        "global_limit_seconds": 2400,
        "manifest_sha256": sha,
        "hxb2_sha256": sha,
        "project_reference_catalog_sha256": sha,
        "images": {"iva": sha, "riva": sha},
        "full_alpha_pass": True,
    }


class SummarizeTests(unittest.TestCase):
    def test_complete_twenty_within_forty_minutes_passes(self):
        self.assertTrue(summarize.evaluate(valid())["pass"])

    def test_bad_conditions_fail_closed(self):
        changes = [
            {"mode": "riva"},
            {"qualification_requested": False},
            {"allow_missing_baseline": True},
            {"accepted_samples": 19},
            {"selected_samples": 19},
            {"finished_samples": 19},
            {"manifest_sample_count": 7},
            {"failed_samples": ["private-sample"]},
            {"global_seconds": 2401},
            {"global_limit_seconds": 2401},
            {"global_seconds": 2399, "global_limit_seconds": 2380},
            {"full_alpha_pass": False},
            {"images": {"iva": "a"*64}},
            {"manifest_sha256": "bogus"},
            {"project_reference_catalog_sha256": None},
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
