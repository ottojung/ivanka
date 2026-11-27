"""Checkpoint and run accounting tests for the posthoc-only diagnostic."""
import json
from pathlib import Path
import tempfile
import unittest

import p1_observed_islands as islands


def sample(case="pcr_jackpot-s000"):
    row = {"case": case, "family": "pcr_jackpot",
           "input_sha256": {"R1": "r1", "R2": "r2", "truth": "t"},
           "output_sha256": {"new": "n"},
           "panel": [{"native_alignment_fraction": {"new": .25},
                      "observed_kmers": 12, "recovered": {"new": 10}}]}
    record = {"case": case, "family": row["family"],
              "input_sha256": row["input_sha256"], "output_sha256": "n",
              "native_alignment_fraction": .25, "observed_unique_kmers": 12,
              "recovered_unique_kmers": 10}
    return row, record


class ObservedIslandsTests(unittest.TestCase):
    def test_runs_and_boundaries(self):
        self.assertEqual(islands.runs([]), {True: [], False: []})
        self.assertEqual(islands.runs([False, True, True, False, True]),
                         {True: [2, 1], False: [1, 1]})
        got = islands.summarize([False]*150 + [True]*6 + [False]*31)
        self.assertEqual(got["longest_supported_bases"], 36)
        self.assertEqual(got["unsupported_runs_ge_150_windows"], 1)
        self.assertEqual(got["unsupported_runs_ge_31_windows"], 2)
        self.assertEqual(islands.summarize([False])["longest_supported_bases"], 0)
        self.assertEqual(islands.summarize([True])["longest_supported_bases"], 31)

    def test_orientation(self):
        seq = "ACGTA"*8
        rev = seq.translate(islands.COMPLEMENT)[::-1]
        self.assertEqual(islands.positions(seq), list(reversed(islands.positions(rev))))
        with self.assertRaises(ValueError):
            islands.positions("N"*31)

    def test_partial_checkpoint_and_drift(self):
        row, record = sample()
        row2, _ = sample("pcr_jackpot-s001")
        header = {"reader_sha256": "a"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.jsonl"
            self.assertEqual(islands.load_checkpoint(path, header, [row, row2]), [])
            with path.open("a") as f:
                islands.append(f, islands.envelope(record))
            self.assertEqual(islands.load_checkpoint(path, header, [row, row2]), [record])
            with self.assertRaisesRegex(ValueError, "source/reader drift"):
                islands.load_checkpoint(path, {"reader_sha256": "b"}, [row])
            with self.assertRaisesRegex(ValueError, "case identity"):
                islands.load_checkpoint(path, header, [row2])

    def test_record_digest_and_partial_line_fail_closed(self):
        row, record = sample()
        header = {"reader_sha256": "a"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.jsonl"
            path.write_text(json.dumps(header) + "\n")
            envelope = islands.envelope(record)
            envelope["record"]["observed_unique_kmers"] = 11
            with path.open("a") as f:
                islands.append(f, envelope)
            with self.assertRaisesRegex(ValueError, "record digest"):
                islands.load_checkpoint(path, header, [row])
            path.write_text(json.dumps(header) + "\n{}")
            with self.assertRaisesRegex(ValueError, "incomplete checkpoint"):
                islands.load_checkpoint(path, header, [row])

    def test_panel_and_duplicate_case_rejected(self):
        row, record = sample()
        record["recovered_unique_kmers"] = 9
        with self.assertRaisesRegex(ValueError, "panel disagreement"):
            islands.check_record(record, row)
        row, record = sample()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.jsonl"
            header = {"reader_sha256": "a"}
            islands.load_checkpoint(path, header, [row])
            with path.open("a") as f:
                islands.append(f, islands.envelope(record))
                islands.append(f, islands.envelope(record))
            with self.assertRaisesRegex(ValueError, "extra case"):
                islands.load_checkpoint(path, header, [row])


if __name__ == "__main__":
    unittest.main()
