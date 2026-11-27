"""Regression tests for exact retained-log interval accounting."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ultradeep_stage_intervals as s


class StageIntervalsTests(unittest.TestCase):
    def test_tampered_prior_rejected_before_historical_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "prior.json"
            p.write_text("{}")
            with patch.object(s, "evaluate") as evaluate:
                with self.assertRaisesRegex(ValueError, "prior diagnostic identity"):
                    s.report(Path(tmp), Path(tmp), p)
                evaluate.assert_not_called()

    def test_changed_log_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "log"
            p.write_text("not the retained bytes")
            with self.assertRaisesRegex(ValueError, "log digest"):
                s.arm(p, s.sha(b"original"), 1)

    def test_bad_duration_and_bad_marker_order_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "log"
            p.write_text("no stage markers")
            digest = s.sha(p.read_bytes())
            for seconds in (True, 0, float("nan"), 2401):
                with self.subTest(seconds=seconds):
                    with self.assertRaisesRegex(ValueError, "official duration"):
                        s.arm(p, digest, seconds)
            with self.assertRaisesRegex(ValueError, "stage_order"):
                s.arm(p, digest, 20)

    def test_retained_report_accounting(self):
        d = Path(__file__).resolve().parents[1] / "docs/bench/diagnostics"
        prior = d / "p1-ultradeep-runtime-20261126.json"
        full = json.loads((d / "p1-ultradeep-stage-intervals-20261127.json").read_bytes())
        old = json.loads(prior.read_bytes())
        self.assertEqual(full["prior_diagnostic_sha256"], s.sha(prior.read_bytes()))
        self.assertEqual(full["case_count"], 16)
        self.assertEqual(full["not_qualification"], True)
        self.assertEqual([r["case"] for r in full["cases"]],
                         [r["case"] for r in old["cases"]])
        for row, pin in zip(full["cases"], old["cases"]):
            for k, key in (("candidate", "candidate_log"), ("frozen", "frozen_stderr")):
                arm = row[k]
                self.assertEqual(arm["log_sha256"], pin["input_sha256"][key])
                self.assertEqual(set(arm["stage_intervals_seconds"]), set(s.STAGES))
                self.assertAlmostEqual(sum(arm["stage_intervals_seconds"].values())
                                       + arm["official_minus_logged_span_seconds"],
                                       arm["official_seconds"])
            for stage in s.STAGES:
                self.assertAlmostEqual(row["delta_seconds"][stage],
                                       row["candidate"]["stage_intervals_seconds"][stage]
                                       - row["frozen"]["stage_intervals_seconds"][stage])
            self.assertAlmostEqual(sum(row["delta_seconds"].values())
                                   + row["outside_logged_span_delta_seconds"],
                                   pin["end_to_end_delta_seconds"])
        for stage in s.STAGES:
            self.assertAlmostEqual(full["stage_delta_seconds"][stage],
                                   sum(r["delta_seconds"][stage] for r in full["cases"]))
        self.assertAlmostEqual(sum(full["stage_delta_seconds"].values())
                               + full["outside_logged_span_delta_seconds"],
                               old["sum_end_to_end_delta_seconds"])


if __name__ == "__main__":
    unittest.main()
