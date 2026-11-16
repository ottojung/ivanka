"""Hermetic real-198 comparator evidence and crash-recovery contracts."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.expanded.comparator_real_first import (
    INVOCATION, PANEL_SHA, discard_success_scratch, history, input_hash,
    preserve_orphan, validate,
)


class ComparatorRealFirstTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = "63902A-V3-3-V3LOOP_S39"
        self.image = "1" * 64
        self.frozen = {"original_inputs": {self.sample: "source-hash"},
                       "images": {"iva": self.image}}
        self.arm = self.root / INVOCATION / self.sample / "iva"
        self.arm.mkdir(parents=True)

    def fake(self, successful=True):
        source = self.arm / "conseq.csv"
        source.write_text("region,consensus-percent-cutoff,sequence\n1,MAX,ACTG\n")
        arm = {"exit_code": 0 if successful else 1,
               "artifact_dir": str(self.arm), "image_id": self.image,
               "seconds": 2.5 if successful else None,
               "metrics": {} if successful else None}
        record = {
            "sample": self.sample, "assembler": "iva",
            "input_sha256": "source-hash", "image_id": self.image,
            "status": "success" if successful else "failed",
            "micall": arm,
        }
        if successful:
            record["final_max"] = {"score": 4.0, "panel_sha256": PANEL_SHA,
                                   "source_output": "conseq.csv",
                                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        else:
            record["error"] = "recorded true MiCall failure"
        (self.arm / "comparator_execution.json").write_text(json.dumps(record))
        (self.root / "results.jsonl").write_text(json.dumps(record)+"\n")
        return record

    def test_success_and_failed_records_remain_distinct(self):
        success = self.fake(True)
        self.assertEqual(validate(success, self.frozen, self.root),
                         (self.sample, "iva"))
        self.assertEqual(len(history(self.root, self.frozen)), 1)
        self.fake(False)
        self.assertEqual(len(history(self.root, self.frozen)), 1)
        self.assertEqual(history(self.root, self.frozen)[(self.sample, "iva")]["status"],
                         "failed")

    def test_tampered_post_micall_score_output_fails_closed(self):
        self.fake(True)
        (self.arm / "conseq.csv").write_text("changed")
        with self.assertRaisesRegex(ValueError, "MiCall final MAX"):
            history(self.root, self.frozen)

    def test_changed_original_fastq_fingerprint_rejected(self):
        self.fake(True)
        row = json.loads((self.root / "results.jsonl").read_text())
        row["input_sha256"] = "wrong source"
        (self.root / "results.jsonl").write_text(json.dumps(row)+"\n")
        with self.assertRaisesRegex(ValueError, "altered frozen physical"):
            history(self.root, self.frozen)

    def test_wrong_assembler_and_image_are_not_reusable(self):
        record = self.fake(True)
        record["assembler"] = "ivanka"
        with self.assertRaisesRegex(ValueError, "altered frozen physical"):
            validate(record, self.frozen, self.root)
        record["assembler"] = "iva"
        record["image_id"] = "other"
        with self.assertRaisesRegex(ValueError, "altered frozen physical"):
            validate(record, self.frozen, self.root)

    def test_prune_only_fsynced_success_preserves_failure_scratch(self):
        saved = self.fake(True)
        scratch = self.arm / "scratch"
        scratch.mkdir()
        (scratch / "unstitched_remap.csv").write_bytes(b"temporary" * 800)
        discard_success_scratch(saved, self.frozen, self.root)
        self.assertFalse(scratch.exists())
        self.assertEqual(len(history(self.root, self.frozen)), 1)
        failed = self.fake(False)
        scratch.mkdir()
        (scratch / "unstitched_remap.csv").write_bytes(b"failed-diagnostics")
        discard_success_scratch(failed, self.frozen, self.root)
        self.assertTrue((scratch / "unstitched_remap.csv").is_file())

    def test_prune_refuses_symlink_to_external_scratch(self):
        saved = self.fake(True)
        external = self.root / "external"
        external.mkdir()
        (external / "preserve-me").write_text("raw")
        (self.arm / "scratch").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe scratch"):
            discard_success_scratch(saved, self.frozen, self.root)
        self.assertTrue((external / "preserve-me").is_file())

    def test_replay_rejects_truncated_or_duplicate_results(self):
        self.fake()
        file = self.root / "results.jsonl"
        old = file.read_text()
        file.write_text(old + "{")
        with self.assertRaisesRegex(ValueError, "truncated"):
            history(self.root, self.frozen)
        file.write_text(old + old)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            history(self.root, self.frozen)

    def test_original_pair_hash_uses_both_real_fastq_files(self):
        p = self.root / "samples" / self.sample
        p.mkdir(parents=True)
        r1 = p / f"{self.sample}_L001_R1_001.fastq.gz"
        r2 = p / f"{self.sample}_L001_R2_001.fastq.gz"
        r1.write_bytes(b"first")
        r2.write_bytes(b"second")
        a = input_hash({"sample": self.sample}, self.root)
        r2.write_bytes(b"altered")
        b = input_hash({"sample": self.sample}, self.root)
        self.assertNotEqual(a, b)

    def test_interruptions_are_preserved_before_retry(self):
        (self.arm / "podman.stderr.log").write_text("interrupted")
        preserve_orphan(self.root, self.sample, "iva")
        self.assertFalse(self.arm.exists())
        prior = list((self.root / "_interrupted").iterdir())
        self.assertEqual(len(prior), 1)
        self.assertEqual((prior[0] / "podman.stderr.log").read_text(),
                         "interrupted")


if __name__ == "__main__":
    unittest.main()
