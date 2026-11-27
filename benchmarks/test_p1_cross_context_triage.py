"""Triage retains the historical threshold context and never asserts qualification."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

import p1_cross_context_triage as triage


class CrossContextTests(unittest.TestCase):
    def test_cases_distinguish_sequence_recovery_from_alignment(self):
        self.assertEqual(triage.classify(.6, .91, .9, .95, .95),
                         "historical_below_native_above")
        self.assertEqual(triage.classify(.6, .65, .9, .95, .95),
                         "both_below_high_kmer_recovery")
        self.assertEqual(triage.classify(.6, .65, .9, .95, .85),
                         "both_below_incomplete_kmer_recovery")
        self.assertEqual(triage.classify(.6, .65, .9, .95, None),
                         "both_below_missing_evidence_denominator")
        self.assertEqual(triage.classify(.95, .65, .9, .95, .95),
                         "historical_above_native_below")
        self.assertEqual(triage.classify(.95, .96, .9, .95, .95), "both_above")

    def test_nonfinite_or_out_of_range_fraction_rejected(self):
        for invalid in (True, -0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                triage.fraction(invalid)

    def test_tampered_report_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "native.json"
            p.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "retained source digest changed"):
                triage.report(p, p, p, Path(tmp))

    def test_truth_identity_checked(self):
        arm = {"per_truth": {"truth_0": {"length": 4, "truth_sha256": triage.sha(b"ACGT"),
                                       "nominal_abundance": .5, "fraction": .75, "score": 3}}}
        self.assertEqual(triage.identity_row(arm, "truth_0", "ACGT", .5), .75)
        with self.assertRaisesRegex(ValueError, "truth identity mismatch"):
            triage.identity_row(arm, "truth_0", "ACGA", .5)
        arm["per_truth"]["truth_0"]["score"] = 2
        with self.assertRaisesRegex(ValueError, "per-truth score mismatch"):
            triage.identity_row(arm, "truth_0", "ACGT", .5)

    def test_retained_report(self):
        docs = Path(__file__).resolve().parents[1] / "docs/bench/diagnostics"
        doc = json.loads((docs / "p1-cross-context-triage-20261127.json").read_bytes())
        self.assertIs(doc["not_qualification"], True)
        self.assertEqual(doc["matched_cases"], 128)
        self.assertEqual(doc["matched_truths"], 192)
        self.assertEqual(doc["ledger_sha256"], triage.LEDGER)
        for field, name in (("native_sha256", "p1-adapter-mode-native-20261126.json"),
                            ("posthoc_sha256", "p1-adapter-mode-posthoc-complete-20261126.json")):
            self.assertEqual(doc[field], triage.sha((docs / name).read_bytes()))
        rows = doc["rows"]
        self.assertEqual(len({(r["case"], r["truth"]) for r in rows}), 192)
        self.assertEqual({r["case"] for r in rows}, triage.CASES)
        for r in rows:
            threshold = .9 * r["historical_best_rival_fraction"]
            self.assertAlmostEqual(r["historical_rival_relative_threshold"], threshold)
            self.assertEqual(r["triage"], triage.classify(
                r["historical_final_candidate_fraction"], r["native_new_alignment_fraction"],
                threshold, r["native_new_observed_recovery"], r["native_new_exclusive_recovery"]))
            self.assertTrue(1 <= r["rival_count"] <= 6)
        self.assertEqual(doc["summaries"]["all"], dict(Counter(r["triage"] for r in rows)))
        for family in {r["family"] for r in rows}:
            self.assertEqual(doc["summaries"][family],
                             dict(Counter(r["triage"] for r in rows if r["family"] == family)))
        self.assertEqual(sum(r["historical_final_candidate_fraction"] + triage.EPS
                             < r["historical_rival_relative_threshold"] for r in rows), 49)


if __name__ == "__main__":
    unittest.main()
