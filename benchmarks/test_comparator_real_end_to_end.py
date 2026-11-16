"""Hermetic full physical comparator orchestration, checkpoint and retry.

This test replaces MiCall with a fake *after* source validation; it neither
generates benchmark numbers nor modifies any original physical input.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import json
import unittest

import benchmarks
from benchmarks.expanded import comparator_real_first as physical


class RealComparatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data = self.base / "frozen-data"
        self.data.mkdir()
        self.output = self.base / "results"
        self.images = {"iva": "1" * 64, "spades": "2" * 64}
        self.rows = [{"sample": "sample_one", "project": "HCV"},
                     {"sample": "sample_two", "project": "NFLHIVDNA"}]
        self.frozen = {
            "schema": "test.frozen.original-pair-provenance",
            "expected_samples": 2, "expected_arms": 4, "qualified": False,
            "original_inputs": {"sample_one": "mate1", "sample_two": "mate2"},
            "images": self.images, "jobs": 2,
        }
        self.calls = []
        fake = ModuleType("benchmarks.podman_full_micall")
        fake.DATA = self.data
        fake.RESULTS = self.output
        fake.run_arm = self.fake_arm
        self.fake_driver = fake

    def fake_arm(self, row, name, image, reference, timeout,
                 invocation, all_projects):
        self.assertEqual(timeout, 1800)
        self.assertTrue(all_projects)
        self.assertIn(name, ("iva", "spades"))
        self.assertEqual(reference is not None,
                         row["project"] == "NFLHIVDNA")
        folder = self.output / invocation / row["sample"] / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "conseq.csv").write_text(
            "region,consensus-percent-cutoff,sequence\nHXB2,MAX,ACTG\n")
        scratch = folder / "scratch"
        scratch.mkdir()
        (scratch / "remap.tmp").write_bytes(b"reproducible")
        self.calls.append((row["sample"], name))
        failed = row["sample"] == "sample_two" and name == "spades"
        return {"artifact_dir": str(folder), "image_id": image,
                "exit_code": 3 if failed else 0,
                "metrics": {} if not failed else None,
                "seconds": 1.25, "error": "genuine tool failure" if failed else ""}

    def execute(self):
        with patch.object(physical, "freeze", return_value=(
                self.frozen, self.rows, [("HXB2", "ACTG")], "ACTG")), \
             patch.object(physical, "TOOLS", ("iva", "spades")), \
             patch.object(physical.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=1 << 40)), \
             patch.object(benchmarks, "podman_full_micall",
                          self.fake_driver, create=True), \
             patch.dict("sys.modules", {
                 "benchmarks.podman_full_micall": self.fake_driver,
             }):
            physical.run(self.data, self.output,
                         self.base / "source-images.json", 2)

    def test_full_orchestration_then_identical_restart(self):
        self.execute()
        journal = (self.output / "results.jsonl").read_text().splitlines()
        self.assertEqual(len(journal), 4)
        self.assertEqual(set(self.calls), {
            ("sample_one", "iva"), ("sample_one", "spades"),
            ("sample_two", "iva"), ("sample_two", "spades"),
        })
        results = [json.loads(line) for line in journal]
        self.assertEqual(sum(x["status"] == "success" for x in results), 3)
        self.assertEqual(sum(x["status"] == "failed" for x in results), 1)
        for row in results:
            folder = self.output / physical.INVOCATION / row["sample"] / row["assembler"]
            self.assertTrue((folder / "conseq.csv").is_file())
            self.assertEqual((folder / "scratch").exists(),
                             row["status"] == "failed")
        marker = json.loads((self.output / "attempt-finished.json").read_text())
        self.assertFalse(marker["qualified"])
        self.assertEqual(marker["arms"], 4)
        self.assertEqual(marker["status"], "ATTEMPTED_4_NOT_RELEASE_QUALIFIED")
        self.assertEqual(marker["cases"], 2)
        self.assertEqual(marker["failed_arms"], 1)
        self.execute()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(len((self.output / "results.jsonl").read_text().splitlines()), 4)

    def test_changed_source_manifest_fails_before_rerun(self):
        self.execute()
        frozen = dict(self.frozen)
        frozen["source_commit"] = "unexpected"
        self.frozen = frozen
        with self.assertRaisesRegex(ValueError, "changed physical cohort"):
            self.execute()
        self.assertEqual(len(self.calls), 4)

    def test_corrupt_frozen_final_output_fails_closed(self):
        self.execute()
        path = self.output / physical.INVOCATION / "sample_one" / "iva" / "conseq.csv"
        path.write_text("changed score artifact")
        with self.assertRaisesRegex(ValueError, "MiCall final MAX"):
            self.execute()
        self.assertEqual(len(self.calls), 4)


if __name__ == "__main__":
    unittest.main()
