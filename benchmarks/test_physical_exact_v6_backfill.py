"""Physical exact-read backfill must bind read witnesses and original retries."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from assembler_bench import physical_exact_v6_backfill as exact


class PhysicalExactTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.original = self.path / "phase-real198"
        self.retries = self.path / "phase-real198-memory-retries"
        self.sample = "V3LOOP_S24"
        self.tool = "spades"
        self.image = "1" * 64
        self.key = hashlib.sha256(self.sample.encode()).hexdigest()+".json"
        self.source = self.original / self.tool / "checkpoints" / self.key
        self.target = self.retries / self.tool / "checkpoints" / self.key
        self.source.parent.mkdir(parents=True)
        self.target.parent.mkdir(parents=True)

    def evidence(self):
        original = {"sample": self.sample, "tool": self.tool,
                    "image_id": self.image, "failed": True,
                    "status": "finished", "input_sha256": "e" * 64,
                    "reference_panel_sha256": "f" * 64,
                    "arm": {"exit_code": 255,
                            "container_wall_seconds": 1800}}
        self.source.write_text(json.dumps(original))
        retry = dict(original, failed=False, arm={
            "exit_code": 0, "artifact_dir": str(self.path)})
        retry.update({
            "resource_timeout_seconds": 3000,
            "original_checkpoint_sha256": exact.digest(self.source)})
        self.target.write_text(json.dumps(retry))
        return retry

    def test_only_source_linked_retry_is_selected(self):
        expected = self.evidence()
        self.assertEqual(exact.choose_checkpoint(
            self.original, self.retries, self.tool,
            self.sample, self.image), expected)

    def test_modified_retry_source_hash_is_rejected(self):
        retry = self.evidence()
        retry["original_checkpoint_sha256"] = "bad"
        self.target.write_text(json.dumps(retry))
        with self.assertRaises(ValueError):
            exact.choose_checkpoint(
                self.original, self.retries, self.tool,
                self.sample, self.image)

    def test_consensus_digest_required_before_postprocessing(self):
        consensus = self.path / "conseq.csv"
        consensus.write_text("consensus\nMAX\n")
        sha = exact.digest(consensus)
        arm = {"failed": False, "arm": {
            "artifact_dir": str(self.path),
            "metrics": {"outputs": {"conseq.csv": {"sha256": sha}}}}}
        published = {"status": "success", "conseq_digest": sha}
        with patch.object(exact, "real_arm", return_value=published),                 patch.object(exact, "choose_checkpoint", return_value=arm):
            source, mates, h = exact.verified_source(
                self.original, self.retries, self.path,
                self.sample, self.tool, self.image, [])
            self.assertEqual((source, h), (consensus, sha))
            self.assertEqual(len(mates), 2)
            consensus.write_text("changed")
            with self.assertRaisesRegex(ValueError, "consensus modified"):
                exact.verified_source(
                    self.original, self.retries, self.path,
                    self.sample, self.tool, self.image, [])

    def test_never_write_under_input_or_results(self):
        for target in (self.original, self.original / "unsafe",
                       self.path / "reads", self.path / "reads/cache"):
            data = self.path / "reads"
            with self.assertRaises(ValueError):
                exact.run(self.original, self.retries, data,
                          target, self.path, self.path,
                          self.path, self.path, 0)


if __name__ == "__main__":
    unittest.main()
