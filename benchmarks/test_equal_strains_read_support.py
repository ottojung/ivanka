"""Equal-strain diagnostic must not confuse two truth identities."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from equal_strains_read_support import evaluate, validate_panel


class EqualStrainsReadSupportTest(unittest.TestCase):
    def setUp(self):
        self.truths = ["A" * 40, "C" * 40]
        self.panel = {f"truth_{i}": {
            "truth_sha256": hashlib.sha256(seq.encode()).hexdigest(),
            "length": len(seq), "nominal_abundance": 0.5,
            "score": 20, "fraction": 0.5,
        } for i, seq in enumerate(self.truths)}

    def test_exact_truth_identity(self):
        arm = {"per_truth": self.panel}
        self.assertEqual(validate_panel(arm, self.truths), self.panel)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            validate_panel(arm, self.truths[::-1])

    def test_invalid_fraction_refused(self):
        arm = {"per_truth": self.panel}
        for value in (float("nan"), True, 0.6, -1):
            self.panel["truth_0"]["fraction"] = value
            with self.assertRaisesRegex(ValueError, "invalid"):
                validate_panel(arm, self.truths)

    def test_missing_panel_refused(self):
        del self.panel["truth_1"]
        with self.assertRaisesRegex(ValueError, "truth panel"):
            validate_panel({"per_truth": self.panel}, self.truths)

    def test_incomplete_cohort_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p / "results.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                evaluate(p, p, p)
