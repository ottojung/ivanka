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
    def test_failed_checkpoint_remains_visible_without_fabricated_score(self):
        from assembler_bench.real_public import measured
        event = {
            "failed": True,
            "iva": {"exit_code": 0, "seconds": 45.,
                    "timing_origin": "micall_in_container_monotonic_v1"},
            "ivanka": {"exit_code": 1, "seconds": None,
                       "timing_origin": None},
        }
        self.assertEqual(measured(event, "iva"), (None, None))
        self.assertEqual(measured(event, "ivanka"), (None, None))
        event["failed"] = False
        with self.assertRaisesRegex(ValueError, "missing score"):
            measured(event, "iva")

    def test_scored_floor_failure_remains_scored(self):
        from assembler_bench.real_public import measured
        event = {
            "failed": True,
            "best_contig_acceptance": {
                "iva_score": 1300., "ivanka_score": 700.,
                "pass": False,
            },
            "iva": {"exit_code": 0, "seconds": 46.,
                    "timing_origin": "micall_in_container_monotonic_v1"},
            "ivanka": {"exit_code": 0, "seconds": 37.,
                       "timing_origin": "micall_in_container_monotonic_v1"},
        }
        self.assertEqual(measured(event, "iva"), (1300., 46.))
        self.assertEqual(measured(event, "ivanka"), (700., 37.))
        event["ivanka"]["seconds"] = -1.
        with self.assertRaisesRegex(ValueError, "valid score or time"):
            measured(event, "ivanka")

    def test_sample_timeout_is_visible_without_claiming_success(self):
        images = {"iva": "a"*64, "ivanka": "b"*64}
        source = {
            "sample": "secret-1", "status": "sample_timeout",
            "failed": True,
            "iva": {"image_id": images["iva"], "exit_code": 0},
            "ivanka": {"image_id": images["ivanka"],
                       "exit_code": 124, "seconds": None},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"sample": "secret-1",
                                        "status": "started"})+"\n"+
                            json.dumps(source)+"\n")
            self.assertEqual(completed(path, {"secret-1"},
                                       "ivanka", images),
                             {"finished": 1, "failed": 1})
            from assembler_bench.real_public import measured
            self.assertEqual(measured(source, "ivanka"), (None, None))
            self.assertEqual(measured(source, "iva"), (None, None))
            source["ivanka"]["image_id"] = "f"*64
            path.write_text(json.dumps({"sample": "secret-1",
                                        "status": "started"})+"\n"+
                            json.dumps(source)+"\n")
            with self.assertRaisesRegex(ValueError, "image identity"):
                completed(path, {"secret-1"}, "ivanka", images)

    def test_error_before_image_start_is_a_reported_failure(self):
        images = {"iva": "a"*64, "ivanka": "b"*64}
        source = {"sample": "secret-1", "status": "error",
                  "failed": True,
                  "iva": {"image_id": images["iva"], "exit_code": 0},
                  "ivanka": {"exit_code": 1,
                             "error": "Podman create failed"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"sample": "secret-1",
                                        "status": "started"})+"\n"+
                            json.dumps(source)+"\n")
            self.assertEqual(completed(path, {"secret-1"},
                                       "ivanka", images),
                             {"finished": 1, "failed": 1})
            source["failed"] = False
            path.write_text(json.dumps({"sample": "secret-1",
                                        "status": "started"})+"\n"+
                            json.dumps(source)+"\n")
            with self.assertRaises(ValueError):
                completed(path, {"secret-1"}, "ivanka", images)

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
