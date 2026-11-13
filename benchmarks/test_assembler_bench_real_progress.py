"""Physical cohort progress must be authentic, aggregate-only and provisional."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from assembler_bench.real_progress import (
    PROGRESS, completed, validate_public,
)


class PhysicalProgressTests(unittest.TestCase):
    def test_aggregate_metadata_has_no_sample_identifiers(self):
        report = {
            "schema": PROGRESS, "expected_samples": 198,
            "status": "incomplete", "run_manifest_sha256": "a"*64,
            "candidates": {name: {"finished": 0, "failed": 0}
                           for name in ("ivanka", "haploflow", "megahit",
                                        "abyss", "spades", "velvet")}}
        validate_public(report)
        bad = copy.deepcopy(report)
        bad["candidates"]["ivanka"]["finished"] = 199
        with self.assertRaises(ValueError):
            validate_public(bad)
        bad = copy.deepcopy(report)
        bad["candidates"]["ivanka"]["sample"] = "sensitive-identifier"
        with self.assertRaises(ValueError):
            validate_public(bad)
        bad = copy.deepcopy(report)
        bad["status"] = "passed"
        with self.assertRaises(ValueError):
            validate_public(bad)

    def test_only_unique_verified_finished_cases_count(self):
        images = {"iva": "a"*64, "ivanka": "b"*64}
        events = [
            {"sample": "secret-1", "status": "started"},
            {"sample": "secret-1", "status": "finished",
             "iva": {"image_id": images["iva"]},
             "ivanka": {"image_id": images["ivanka"]},
             "failed": False},
            {"sample": "secret-2", "status": "started"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            def write(rows):
                path.write_text("".join(json.dumps(r)+"\n" for r in rows))
            write(events)
            self.assertEqual(completed(path, {"secret-1", "secret-2"},
                                       "ivanka", images),
                             {"finished": 1, "failed": 0})
            write(events + [events[1]])
            with self.assertRaises(ValueError):
                completed(path, {"secret-1", "secret-2"}, "ivanka", images)
            bad = copy.deepcopy(events)
            bad[1]["ivanka"]["image_id"] = "c"*64
            write(bad)
            with self.assertRaises(ValueError):
                completed(path, {"secret-1", "secret-2"}, "ivanka", images)
            bad = copy.deepcopy(events)
            bad[1]["sample"] = "unknown"
            write(bad)
            with self.assertRaises(ValueError):
                completed(path, {"secret-1", "secret-2"}, "ivanka", images)


if __name__ == "__main__":
    unittest.main()
