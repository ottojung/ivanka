"""Recovery never launders failed, partial, duplicate or mixed-invocation data."""
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.expanded.physical198_recovery_journal import combine, read_journal


def event(name, status, source="first", failed=False):
    return {"sample": name, "status": status, "failed": failed,
            "invocation": source}


def journal(path, events):
    path.write_text("".join(json.dumps(x) + "\n" for x in events))
    return read_journal(path, {"A", "B", "C"})


class RecoveryJournalTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.a = Path(self.dir.name) / "original.jsonl"
        self.b = Path(self.dir.name) / "recovery.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    def test_valid_distinct_source_and_recovery(self):
        original = journal(self.a, [event("A", "started"),
                                    event("A", "finished"),
                                    event("B", "started")])
        recovered = journal(self.b, [event("B", "started", "second"),
                                     event("B", "finished", "second"),
                                     event("C", "started", "second"),
                                     event("C", "finished", "second")])
        merged = combine(original, recovered, {"A", "B", "C"}, {"B", "C"})
        self.assertEqual(set(merged), {"A", "B", "C"})

    def test_incomplete_recovery_rejected(self):
        first = journal(self.a, [event("A", "started"), event("A", "finished")])
        second = journal(self.b, [event("B", "started", "second")])
        with self.assertRaisesRegex(ValueError, "recovery missing"):
            combine(first, second, {"A", "B"}, {"B"})

    def test_duplicate_and_failed_events_rejected(self):
        for bad in (
            [event("A", "started"), event("A", "started")],
            [event("A", "finished")],
            [event("A", "started"), event("A", "finished", failed=True)],
            [event("A", "started"), event("A", "error")],
            [event("A", "started"), event("A", "finished"), event("A", "finished")],
            [event("A", "started"), event("B", "finished", "second")],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                journal(self.a, bad)

    def test_source_completion_must_not_be_reused(self):
        original = journal(self.a, [event("A", "started"), event("A", "finished")])
        recovered = journal(self.b, [event("A", "started", "second"),
                                     event("A", "finished", "second")])
        with self.assertRaisesRegex(ValueError, "duplicate completed"):
            combine(original, recovered, {"A"}, set())

    def test_truncated_line_rejected(self):
        self.a.write_text(json.dumps(event("A", "started")))
        with self.assertRaisesRegex(ValueError, "unterminated"):
            read_journal(self.a, {"A"})

    def test_same_invocation_rejected(self):
        original = journal(self.a, [event("A", "started"), event("A", "finished")])
        recovered = journal(self.b, [event("B", "started"), event("B", "finished")])
        with self.assertRaisesRegex(ValueError, "separately identified"):
            combine(original, recovered, {"A", "B"}, {"B"})


if __name__ == "__main__":
    unittest.main()
