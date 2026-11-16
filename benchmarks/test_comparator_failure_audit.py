"""Tamper-evident read-only comparator diagnosis and status semantics."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.expanded.comparator_failure_audit import classify, summarize
from benchmarks.expanded.comparator_first import TOOLS
from benchmarks.expanded.comparator_real_first import INVOCATION, PANEL_SHA


class ComparatorFailureAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = {tool: str(i + 1) * 64 for i, tool in enumerate(TOOLS)}
        self.inputs = {f"sample{i:03d}": "source-hash" for i in range(198)}
        self.manifest = {
            "expected_samples": 198, "expected_arms": 1188,
            "qualified": False, "images": self.images,
            "original_inputs": self.inputs, "source_commit": "pinned-SHA",
        }
        (self.root / "run_manifest.json").write_text(
            json.dumps(self.manifest))
        (self.root / "results.jsonl").write_text("")

    def arm(self, tool, sample, failure=None):
        folder = self.root / INVOCATION / sample / tool
        folder.mkdir(parents=True)
        source = folder / "conseq.csv"
        source.write_text("region,consensus-percent-cutoff,sequence\nHXB2,MAX,ACTG\n")
        record = {
            "sample": sample, "assembler": tool,
            "input_sha256": "source-hash", "image_id": self.images[tool],
            "status": "failed" if failure else "success",
            "micall": {
                "artifact_dir": str(folder), "image_id": self.images[tool],
                "exit_code": 1 if failure else 0,
                "seconds": 1.5, "metrics": {},
            },
        }
        if failure:
            record["error"] = failure
        else:
            record["final_max"] = {
                "score": 4.0, "source_output": "conseq.csv",
                "panel_sha256": PANEL_SHA,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        (folder / "comparator_execution.json").write_text(json.dumps(record))
        with (self.root / "results.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        return record

    def test_failed_podman_wait_is_never_a_biological_loss_or_win(self):
        fail = ("Benchmark: detached Podman wait failure: "
                "Podman wait returned invalid exit status "
                "(bytes=2 sha256_prefix=1bad6b8cf97131fc)")
        self.arm("haploflow", "sample000", fail)
        self.arm("iva", "sample001")
        result = summarize(self.root)
        self.assertEqual(result["observed_terminal_arms"], 2)
        self.assertEqual(result["scored_success"], 1)
        self.assertEqual(result["failed_arms"], 1)
        self.assertEqual(result["remaining_arms"], 1186)
        self.assertEqual(result["by_tool"]["haploflow"]["failure_causes"],
                         {"unverified_podman_wait": 1})
        self.assertTrue(result["failed_arms_are_not_scored_wins"])
        self.assertEqual(result["unverified_podman_exit_samples"],
                         ["haploflow:sample000"])

    def test_corrupt_final_consensus_rejected(self):
        self.arm("iva", "sample000")
        target = self.root / INVOCATION / "sample000" / "iva" / "conseq.csv"
        target.write_text("altered")
        with self.assertRaisesRegex(ValueError, "MiCall final MAX"):
            summarize(self.root)

    def test_changed_image_and_duplicate_are_rejected(self):
        row = self.arm("iva", "sample000")
        journal = self.root / "results.jsonl"
        journal.write_text(json.dumps({**row, "image_id": "wrong"}) + "\n")
        with self.assertRaisesRegex(ValueError, "altered frozen"):
            summarize(self.root)
        journal.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize(self.root)

    def test_partial_line_fails_closed(self):
        self.arm("iva", "sample000")
        journal = self.root / "results.jsonl"
        journal.write_bytes(journal.read_bytes() + b"{")
        with self.assertRaisesRegex(ValueError, "journal snapshot interrupted"):
            summarize(self.root)

    def test_missing_or_malformed_original_input_proof_rejected(self):
        self.manifest["original_inputs"] = {"sample000": "source-hash"}
        (self.root / "run_manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "invalid frozen"):
            summarize(self.root)

    def test_classification_does_not_invent_failures(self):
        self.assertEqual(classify({"status": "failed", "error": "unexpected",
                                   "micall": {"exit_code": 0}}),
                         "unclassified_failed_attempt")
        self.assertEqual(classify({"status": "failed", "error": "timed out",
                                   "micall": {"exit_code": 124}}), "timeout")
        self.assertEqual(classify({"status": "success"}), "scored_success")


if __name__ == "__main__":
    unittest.main()
