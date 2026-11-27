import json
import unittest
from pathlib import Path

from equal_strain_cross_context import evaluate

ROOT = Path(__file__).resolve().parents[1] / "docs/bench/diagnostics"


class CrossContextTest(unittest.TestCase):
    def setUp(self):
        self.prior = (ROOT / "equal-strains-read-support-20261126.json").read_bytes()
        self.new = (ROOT / "p1-adapter-mode-posthoc-partial-20261126.json").read_bytes()

    def test_retained_comparison(self):
        result = evaluate(self.prior, self.new)
        expected = json.loads((ROOT / "equal-strains-cross-context-20261126.json").read_bytes())
        self.assertEqual(result, expected)
        self.assertEqual((result["improved"], result["equal"], result["regressed"]), (14, 2, 0))

    def test_input_drift(self):
        prior = json.loads(self.prior)
        prior["cases"][0]["input_sha256"]["r1"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input_drift"):
            evaluate(json.dumps(prior).encode(), self.new)

    def test_denominator_drift(self):
        prior = json.loads(self.prior)
        prior["cases"][0]["read_observed_exclusive_truth_kmers"] += 1
        with self.assertRaisesRegex(ValueError, "denominator_drift"):
            evaluate(json.dumps(prior).encode(), self.new)
