import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .qualification_scan import load_jsonl


class ScanTests(unittest.TestCase):
    def test_duplicate_result_fails_closed(self):
        with TemporaryDirectory() as d:
            f = Path(d) / "results.jsonl"
            row = json.dumps({"sample": "s", "tool": "iva"})
            f.write_text(row + "\n" + row + "\n")
            with self.assertRaises(ValueError):
                load_jsonl(f)

    def test_incomplete_line_fails_closed(self):
        with TemporaryDirectory() as d:
            f = Path(d) / "results.jsonl"
            f.write_text('{"sample":"s"}')
            with self.assertRaises(ValueError):
                load_jsonl(f)

    def test_audit_can_retain_multiple_invocations(self):
        with TemporaryDirectory() as d:
            f = Path(d) / "audit.jsonl"
            f.write_text('{"container":"x"}\n{"container":"y"}\n')
            self.assertEqual(len(load_jsonl(f, unique=False)), 2)
