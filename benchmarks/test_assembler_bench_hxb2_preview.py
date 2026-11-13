"""Verify the public HXB2 preview never leaks private evidence or invents wins."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assembler_bench.hxb2_preview import checked_run, pinned_truth, preview
from assembler_bench.site_build import SITE, validate_public_site
from expanded.adapters import ASSEMBLERS


class Hxb2PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = json.loads((SITE / "data/runs.json").read_text())
        cls.hxb2 = next(r for r in source["runs"]
                        if r.get("hxb2_truth_verified") is True)

    def test_public_preview_is_anonymized_and_provisional(self):
        run = self.hxb2
        self.assertEqual(run["status"], "incomplete")
        self.assertEqual(run["expanded_status"], "incomplete")
        self.assertFalse(run["eligible_for_expanded"])
        self.assertEqual(run["psi"], {})
        self.assertEqual(run["cohort"], "synthetic")
        self.assertEqual(run["expected_sample_count"], 400)
        self.assertGreaterEqual(run["sample_count"], 0)
        self.assertLessEqual(run["sample_count"], 400)
        self.assertEqual(len(run["samples"]), run["sample_count"])
        self.assertEqual(set(run["tools"]), set(ASSEMBLERS))
        self.assertEqual(len(run["images"]), 7)
        for sample in run["samples"]:
            self.assertRegex(sample["alias"], r"^H[0-9]{3}$")
            self.assertEqual(set(sample["score"]), set(ASSEMBLERS))
            self.assertEqual(set(sample["seconds"]), set(ASSEMBLERS))
            self.assertEqual(sample["outcome"],
                             "failure" if sample["failures"] else "success")
        serialized = json.dumps(run)
        for secret in ("/workspace/", ".fastq", "hidden-truth",
                       "original_sample", "patient_id", "sample_id"):
            self.assertNotIn(secret, serialized)

    def test_failures_are_null_not_artificial_zeros(self):
        run = self.hxb2
        for sample in run["samples"]:
            for tool in ASSEMBLERS:
                if tool in sample["failures"]:
                    self.assertIsNone(sample["score"][tool])
                    self.assertIsNone(sample["seconds"][tool])
                else:
                    self.assertIsInstance(sample["score"][tool], (float, int))
                    self.assertGreater(sample["seconds"][tool], 0)

    def test_site_refuses_ineligible_hxb2_failure_concealment(self):
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            dest = Path(temp)/"site"
            shutil.copytree(SITE, dest)
            original = json.loads((dest/"data/runs.json").read_text())
            edited = copy.deepcopy(original)
            target = next(r for r in edited["runs"]
                          if r.get("hxb2_truth_verified") is True)
            target["status"] = "passed-original-only"
            (dest/"data/runs.json").write_text(json.dumps(edited))
            with self.assertRaises(ValueError):
                validate_public_site(dest)
            edited = copy.deepcopy(original)
            target = next(r for r in edited["runs"]
                          if r.get("hxb2_truth_verified") is True)
            target["psi"] = {"runtime": {"positive_all_nonnegative": True}}
            (dest/"data/runs.json").write_text(json.dumps(edited))
            with self.assertRaisesRegex(ValueError, "HXB2"):
                validate_public_site(dest)

    def test_missing_or_tampered_assembler_measurements_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            dest = Path(temp)/"site"
            shutil.copytree(SITE, dest)
            original = json.loads((dest/"data/runs.json").read_text())
            edited = copy.deepcopy(original)
            run = next(r for r in edited["runs"] if r.get("hxb2_truth_verified"))
            if run["samples"]:
                sample = run["samples"][0]
                tool = sample["failures"][0] if sample["failures"] else "ivanka"
                if tool not in sample["failures"]:
                    sample["failures"].append(tool)
                sample["outcome"] = "failure"
                sample["floor_ok"] = None
                sample["score"][tool] = 0.0
            else:
                run["sample_count"] = 1
            (dest/"data/runs.json").write_text(json.dumps(edited))
            with self.assertRaises(ValueError):
                validate_public_site(dest)
            edited = copy.deepcopy(original)
            run = next(r for r in edited["runs"] if r.get("hxb2_truth_verified"))
            if run["samples"]:
                run["samples"][0]["alias"] = "/workspace/private"
            else:
                run["source_commit"] = "/workspace/private"
            (dest/"data/runs.json").write_text(json.dumps(edited))
            with self.assertRaises(ValueError):
                validate_public_site(dest)

    def test_source_attestation_and_row_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = {
                "schema": "ivanka.expanded.micall_synthetic.v2",
                "expected": 400, "limit": None,
                "source_truth": pinned_truth()[1],
                "status": "INCOMPLETE", "qualified": False,
                "score": "micall_final_dominant_truth_v2",
                "timer": "micall_in_container_monotonic_v1",
                "benchmark_sources_sha256": {},
                "images": {name: "a"*64 for name in ASSEMBLERS},
            }
            (root/"run_manifest.json").write_text(json.dumps(fake))
            (root/"results.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "source SHA"):
                checked_run(root)

    def test_preview_incomplete_cannot_be_reported_as_qualified(self):
        values = {
            tool: {"status": "success", "score": 0.9, "seconds": 12.0}
            for tool in ASSEMBLERS
        }
        values["abyss"] = {"status": "failed", "score": 0.0, "seconds": None}
        record = {
            "id": "clonal-s000", "family": "clonal",
            "results": values,
        }
        manifest = {
            "images": {tool: "b"*64 for tool in ASSEMBLERS},
            "source_truth": {"reference_manifest_sha256": "c"*64},
            "benchmark_sources_sha256": {},
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "run_manifest.json").write_text(json.dumps(manifest))
            with patch("assembler_bench.hxb2_preview.checked_run",
                       return_value=(manifest, [record], "d"*64)):
                run = preview(root)
        self.assertEqual(run["status"], "incomplete")
        self.assertFalse(run["eligible_for_expanded"])
        self.assertEqual(run["sample_count"], 1)
        self.assertEqual(run["samples"][0]["score"]["abyss"], None)
        self.assertEqual(run["samples"][0]["seconds"]["abyss"], None)
        self.assertEqual(run["samples"][0]["outcome"], "failure")
        self.assertEqual(run["psi"], {})


if __name__ == "__main__":
    unittest.main()
