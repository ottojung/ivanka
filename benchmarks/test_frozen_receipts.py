"""All original 4,634 executions remain independently reusable."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.frozen_receipts import INDEX, attest

ROOT = Path("/workspace/micall-frozen-seven-20261117")
ORIGINAL_READ = Path.read_bytes


class FrozenResultsTests(unittest.TestCase):
    def test_all_4634_original_successes_and_failures_reused(self):
        if not ROOT.is_dir():
            self.skipTest("frozen original 198+464 archive unavailable")
        report = attest(ROOT)
        self.assertEqual(report["result_receipt_index_sha256"], INDEX)
        self.assertEqual(report["total"], 4634)
        self.assertEqual(report["synthetic_failed_arms"], 205)
        self.assertEqual(report["physical_success_conseq_sha_verified"], 1148)
        self.assertEqual(report["synthetic_success_conseq_sha_verified"], 3043)

    def test_tampered_consensus_file_is_detected(self):
        if not ROOT.is_dir():
            self.skipTest("frozen original results unavailable")

        def tamper(path):
            data = ORIGINAL_READ(path)
            if Path(path).parts[-3:] == (
                    "clonal-s000", "ivanka", "conseq.csv"):
                return data + b"INVALID_MODIFICATION"
            return data

        with (
            patch.object(Path, "read_bytes", autospec=True,
                         side_effect=tamper),
            self.assertRaisesRegex(ValueError, "consensus bytes differ"),
        ):
            attest(ROOT)

    def test_single_existing_record_mutation_is_detected(self):
        if not ROOT.is_dir():
            self.skipTest("frozen original 198+464 archive unavailable")

        def tamper(path):
            data = ORIGINAL_READ(path)
            if Path(path).parts[-3:] == (
                    "clonal-s000", "ivanka", "execution.json"):
                entry = json.loads(data)
                entry["score"] = -999999
                return json.dumps(entry).encode()
            return data

        with (
            patch.object(Path, "read_bytes", autospec=True,
                         side_effect=tamper),
            self.assertRaisesRegex(ValueError, "historical results changed"),
        ):
            attest(ROOT)


if __name__ == "__main__":
    unittest.main()
