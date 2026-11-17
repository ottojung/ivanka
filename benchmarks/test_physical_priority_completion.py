"""The synthetic cohort must wait for all 198 authenticated physical Ivanka attempts."""
import json
from pathlib import Path
import tempfile
import unittest

from physical_ivanka_completion import SCHEMA, SIX, completed, digest, six_completed


class PhysicalPriorityCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = {tool: f"{i+1:x}" * 64
                       for i, tool in enumerate((*SIX, "ivanka"))}

    def six(self):
        info = {
            "schema": "ivanka.expanded.comparators_first_real.v1",
            "expected_samples": 198,
            "ivanka_deferred": True,
            "images": {name: self.images[name] for name in SIX},
        }
        manifest = self.root / "run_manifest.json"
        manifest.write_text(json.dumps(info))
        summary = {
            "schema": info["schema"], "samples": 198,
            "tools": list(SIX), "ivanka_deferred": True,
            "manifest_sha256": digest(manifest),
        }
        (self.root / "attempt_summary.json").write_text(json.dumps(summary))
        for name in SIX:
            folder = self.root / name / "checkpoints"
            folder.mkdir(parents=True)
            for i in range(198):
                (folder / f"{i:03}.json").write_text("{}")

    def seven(self):
        folder = self.root / "ivanka"
        checkpoints = folder / "checkpoints"
        checkpoints.mkdir(parents=True)
        records = []
        for i in range(198):
            (checkpoints / f"{i:03}.json").write_text("{}")
            records.append({
                "sample": f"physical-{i:03}", "status": "finished",
                "tool": "ivanka", "image_id": self.images["ivanka"],
                "failed": bool(i % 11 == 0),
            })
        journal = folder / "results.jsonl"
        journal.write_text("".join(json.dumps(record) + "\n" for record in records))
        from physical_ivanka_completion import __file__ as source
        proof = {
            "schema": SCHEMA, "samples": 198,
            "terminal_count": 198, "image_sha256": self.images["ivanka"],
            "original_manifest_sha256": digest(self.root / "run_manifest.json"),
            "completion_source_sha256": digest(source),
            "journal_sha256": digest(journal),
            "successful": sum(not row["failed"] for row in records),
            "failed": sum(row["failed"] for row in records),
        }
        (folder / "attempt_summary.json").write_text(json.dumps(proof))

    def test_synthetic_blocked_until_all_six_and_ivanka_complete(self):
        self.assertFalse(six_completed(self.root, self.images))
        self.assertFalse(completed(self.root, self.images))
        self.six()
        self.assertTrue(six_completed(self.root, self.images))
        self.assertFalse(completed(self.root, self.images))
        self.seven()
        self.assertTrue(completed(self.root, self.images))

    def test_missing_original_physical_checkpoint_blocks_handoff(self):
        self.six()
        (self.root / "spades/checkpoints/014.json").unlink()
        with self.assertRaisesRegex(ValueError, "198 checkpoints"):
            completed(self.root, self.images)

    def test_mismatched_ivanka_output_blocks_handoff(self):
        self.six()
        self.seven()
        journal = self.root / "ivanka/results.jsonl"
        journal.write_text(journal.read_text().replace("finished", "started", 1))
        with self.assertRaisesRegex(ValueError, "certificate"):
            completed(self.root, self.images)

    def test_six_only_completion_not_enough(self):
        self.six()
        self.assertFalse(completed(self.root, self.images))
        (self.root / "ivanka").mkdir()
        for i in range(197):
            p = self.root / "ivanka/checkpoints"
            p.mkdir(exist_ok=True)
            (p / f"{i:03}.json").write_text("{}")
        self.assertFalse(completed(self.root, self.images))

    def test_wrong_six_image_or_source_blocks(self):
        self.six()
        other = dict(self.images)
        other["iva"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "source/completion"):
            completed(self.root, other)


if __name__ == "__main__":
    unittest.main()
