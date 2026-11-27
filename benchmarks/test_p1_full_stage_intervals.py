import json
import tempfile
import unittest
from pathlib import Path

import p1_full_stage_intervals as stage


class FullStageTests(unittest.TestCase):
    def test_ledger_digest_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "results.jsonl"
            p.write_bytes(b"{}\n")
            with self.assertRaisesRegex(ValueError, "ledger digest mismatch"):
                stage.ledger(p, "candidate")

    def test_mismatched_input_is_rejected_before_reading_outputs(self):
        a = {"input_sha256": "a" * 64, "family": "clonal"}
        b = {"input_sha256": "b" * 64, "family": "clonal"}
        with self.assertRaisesRegex(ValueError, "unmatched case identity"):
            stage.pair("clonal-s000", Path("/missing"), Path("/missing"), a, b)

    def test_timing_record_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "podman.log").write_text("")
            (p / "timing.json").write_text(json.dumps({
                "exit_code": 0, "seconds": 4, "timing_origin": stage.TIMING_ORIGIN}))
            with self.assertRaisesRegex(ValueError, "timing record and ledger disagree"):
                stage.timed_arm(p, {"seconds": 5}, "candidate")

    def test_retained_report(self):
        path = Path(__file__).resolve().parents[1] / "docs/bench/diagnostics"
        report = json.loads((path / "p1-full-stage-intervals-20261127.json").read_bytes())
        self.assertIs(report["not_qualification"], True)
        self.assertEqual(report["requested_cases"], 464)
        self.assertEqual(report["measured_pairs"], 448)
        self.assertEqual(len({r["case"] for r in report["cases"]}), 464)
        self.assertEqual(report["ledger_sha256"], {k: v[0] for k, v in stage.PINS.items()})
        rows = [r for r in report["cases"] if r["status"] == "measured"]
        self.assertEqual(len(rows), 448)
        self.assertEqual(sum(r["status"] == "not_evaluated" for r in report["cases"]), 16)
        for r in rows:
            for a in ("candidate", "frozen"):
                arm = r[a]
                self.assertEqual(set(arm["stage_intervals_seconds"]), set(stage.STAGES))
                self.assertAlmostEqual(sum(arm["stage_intervals_seconds"].values())
                                       + arm["official_minus_logged_span_seconds"],
                                       arm["seconds"])
            self.assertEqual(r["same_conseq_bytes"],
                             r["candidate"]["conseq_sha256"] == r["frozen"]["conseq_sha256"])
            for name in stage.STAGES:
                self.assertAlmostEqual(r["stage_delta_seconds"][name],
                                       r["candidate"]["stage_intervals_seconds"][name]
                                       - r["frozen"]["stage_intervals_seconds"][name])
        self.assertEqual(stage.summarize(rows), report["summaries"]["all"])
        identical = [r for r in rows if r["same_conseq_bytes"] and r["same_ordered_unstitched"]]
        self.assertEqual(len(identical), 322)
        self.assertEqual(stage.summarize(identical),
                         report["summaries"]["output_identity:(True, True)"])
        self.assertTrue(all(r["same_score"] for r in rows if r["same_conseq_bytes"]))
        self.assertEqual(stage.summarize([r for r in identical if r["family"] != "ultradeep"]),
                         report["summaries"]["identical_excluding_ultradeep"])


if __name__ == "__main__":
    unittest.main()
