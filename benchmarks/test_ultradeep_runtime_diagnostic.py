"""Check diagnostic timing parsing and separation of the unmeasured residual."""
from pathlib import Path
import tempfile
import unittest

from ultradeep_runtime_diagnostic import compare_times, ledger, native_duration


class UltradeepRuntimeDiagnosticTest(unittest.TestCase):
    def test_native_duration(self):
        self.assertEqual(native_duration("INFO: Assembled 2 contigs in 0:01:02.25"), (2, 62.25))
        for text in ("", "Assembled 2 contigs in 0:00:60",
                     "Assembled 1 contigs in 0:00:01\nAssembled 1 contigs in 0:00:02"):
            with self.assertRaises(ValueError):
                native_duration(text)

    def test_unattributed_delta(self):
        r = compare_times(200, 100, 4, 2)
        self.assertEqual(r["native_delta_seconds"], 2)
        self.assertEqual(r["unattributed_delta_seconds"], 98)
        with self.assertRaises(ValueError):
            compare_times(3, 2, 4, 1)

    def test_incomplete_ledger_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "results.jsonl"
            p.write_text("")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                ledger(p)
