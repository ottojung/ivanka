import copy
import hashlib
import json
import unittest
from pathlib import Path

from native_adapter_mode_readback import validate

DOCS = Path(__file__).resolve().parents[1] / "docs/bench/diagnostics"


class NativeReadbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = (DOCS / "p1-adapter-mode-native-20261126.json").read_bytes()
        cls.posthoc = json.loads(
            (DOCS / "p1-adapter-mode-posthoc-partial-20261126.json").read_bytes())

    def test_exact_retained_reports(self):
        result = validate(self.native, self.posthoc)
        self.assertEqual(result["native_arms"], 256)
        self.assertEqual(result["identical_pairs"], 112)
        self.assertEqual(result["posthoc_completed"], 69)
        self.assertEqual(len(result["posthoc_not_evaluated"]), 59)
        self.assertEqual(len(result["changed_pairs"]), 16)
        self.assertTrue(all(x.startswith("pcr_jackpot-") for x in result["changed_pairs"]))

    def test_empty_seed_flag_mismatch(self):
        native = json.loads(self.native)
        record = next(r for r in native["records"] if not r["seeded"])
        record["seeded"] = True
        blob = json.dumps(native).encode()
        posthoc = copy.deepcopy(self.posthoc)
        posthoc["native_report_sha256"] = hashlib.sha256(blob).hexdigest()
        with self.assertRaisesRegex(ValueError, "adapter_seed_mode"):
            validate(blob, posthoc)

    def test_duplicate_arm_rejected(self):
        native = json.loads(self.native)
        native["records"][1] = native["records"][0]
        blob = json.dumps(native).encode()
        posthoc = copy.deepcopy(self.posthoc)
        posthoc["native_report_sha256"] = hashlib.sha256(blob).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate_arm"):
            validate(blob, posthoc)

    def test_posthoc_output_drift(self):
        posthoc = copy.deepcopy(self.posthoc)
        posthoc["cases"][0]["output_sha256"]["new"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "posthoc_output_drift"):
            validate(self.native, posthoc)
