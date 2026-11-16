"""Hermetic tests: stage lengths cannot silently rewrite a frozen score."""
import csv
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.expanded.stitch_stage_diagnostics import compare


class StitchStageDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.left = Path(self.tmp.name) / "old"
        self.right = Path(self.tmp.name) / "new"

    def make_run(self, root, source, image, cases):
        root.mkdir()
        manifest = {"cohort_sha256": "frozen-cohort",
                    "ivanka_source_commit": source,
                    "images": {"ivanka": image}, "qualified": False}
        (root / "run_manifest.json").write_text(json.dumps(manifest))
        rows = []
        for name, family, score, seconds, native, remap, final in cases:
            rows.append({
                "id": name, "family": family,
                "input_sha256": "input-" + name,
                "truth_validation": {"valid": True},
                "ivanka": {"score": score, "seconds": seconds,
                           "status": "success"},
            })
            arm = root / name / "ivanka"
            arm.mkdir(parents=True)
            for filename, field, sequences in (
                ("unstitched_contigs.csv", "contig", native),
                ("remap_conseq.csv", "sequence", remap),
                ("conseq.csv", "sequence", final),
            ):
                with (arm / filename).open("w") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["sample", field])
                    writer.writeheader()
                    for seq in sequences:
                        writer.writerow({"sample": name, field: seq})
        payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (root / "results.jsonl").write_bytes(payload)
        (root / "attempt_complete_marker.json").write_text(json.dumps({
            "samples_attempted": len(cases),
            "results_sha256": sha256(payload).hexdigest(),
            "run_manifest_sha256": sha256(
                (root / "run_manifest.json").read_bytes()).hexdigest(),
            "ivanka_source_commit": source}))

    def fixture(self):
        cases0 = [
            ("complex_mixture-s011", "complex_mixture", 9400, 150,
             ["A" * 9626], ["A" * 9626], ["A" * 9400]),
            ("coverage_hole-s002", "coverage_hole", 4300, 120,
             ["C" * 4428], ["C" * 4428], ["C" * 4300]),
        ]
        cases1 = [
            ("complex_mixture-s011", "complex_mixture", 4604, 100,
             ["A" * 9626, "G" * 10441], ["A" * 14433], ["A" * 14312]),
            ("coverage_hole-s002", "coverage_hole", 7063, 90,
             ["C" * 4428, "G" * 4142], ["C" * 8570], ["C" * 8412]),
        ]
        self.make_run(self.left, "before-commit", "image-old", cases0)
        self.make_run(self.right, "after-commit", "image-new", cases1)

    def test_full_frozen_comparison_keeps_helpful_and_harmful_joins(self):
        self.fixture()
        result = compare(self.left, self.right, 2)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["score_worse"], 1)
        self.assertEqual(result["score_improved"], 1)
        self.assertEqual(result["faster"], 2)
        self.assertEqual(result["examples_of_largest_regression"][0],
                         "complex_mixture-s011")
        bad, good = result["samples"]
        self.assertEqual(bad["remap_extension_after"], 3992)
        self.assertEqual(bad["remap_extension_before"], 0)
        self.assertEqual(good["remap_extension_after"], 4142)
        self.assertEqual(good["score_delta"], 2763)
        self.assertIn("sha256", bad["after"]["remap_targets"])

    def test_modified_completion_sha_refuses_comparison(self):
        self.fixture()
        file = self.right / "results.jsonl"
        file.write_bytes(file.read_bytes().replace(b"4604", b"9999"))
        with self.assertRaisesRegex(ValueError, "unauthenticated"):
            compare(self.left, self.right, 2)

    def test_different_original_input_refuses_comparison(self):
        self.fixture()
        file = self.right / "results.jsonl"
        records = [json.loads(line) for line in file.read_text().splitlines()]
        records[0]["input_sha256"] = "other"
        raw = "".join(json.dumps(row) + "\n" for row in records)
        file.write_text(raw)
        marker = self.right / "attempt_complete_marker.json"
        data = json.loads(marker.read_text())
        data["results_sha256"] = sha256(raw.encode()).hexdigest()
        marker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "source or evaluator truth"):
            compare(self.left, self.right, 2)

    def test_missing_stage_file_is_an_error_not_a_win(self):
        self.fixture()
        (self.right / "complex_mixture-s011/ivanka/remap_conseq.csv").unlink()
        with self.assertRaisesRegex(ValueError, "missing stage evidence"):
            compare(self.left, self.right, 2)

    def test_cannot_compare_two_identical_images(self):
        self.fixture()
        manifest = self.right / "run_manifest.json"
        data = json.loads(manifest.read_text())
        data["images"]["ivanka"] = "image-old"
        manifest.write_text(json.dumps(data))
        marker = self.right / "attempt_complete_marker.json"
        completion = json.loads(marker.read_text())
        completion["run_manifest_sha256"] = sha256(manifest.read_bytes()).hexdigest()
        marker.write_text(json.dumps(completion))
        with self.assertRaisesRegex(ValueError, "same immutable image"):
            compare(self.left, self.right, 2)

    def test_failed_arm_does_not_contribute_as_positive_score(self):
        self.fixture()
        journal = self.right / "results.jsonl"
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        records[0]["ivanka"]["status"] = "failure"
        raw = "".join(json.dumps(row) + "\n" for row in records)
        journal.write_text(raw)
        marker = self.right / "attempt_complete_marker.json"
        data = json.loads(marker.read_text())
        data["results_sha256"] = sha256(raw.encode()).hexdigest()
        marker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "non-success"):
            compare(self.left, self.right, 2)


if __name__ == "__main__":
    unittest.main()
