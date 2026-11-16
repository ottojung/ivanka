"""Hermetic end-to-end fixed synthetic comparator checkpoint and restart."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from benchmarks.expanded import comparator_first as synthetic
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from benchmarks.expanded.micall_synthetic_constants import TIMING_ORIGIN


class SyntheticComparatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.out = self.home / "results"
        self.images = {"iva": "1" * 64, "spades": "2" * 64}
        self.cases = [
            ("clonal-s000", self.home / "case1",
             {"family": "clonal", "sha256": {
                 "reads/R1.fastq.gz": "a1", "reads/R2.fastq.gz": "a2"}}),
            ("minority_30pct-s001", self.home / "case2",
             {"family": "minority_30pct", "sha256": {
                 "reads/R1.fastq.gz": "b1", "reads/R2.fastq.gz": "b2"}}),
        ]
        self.frozen = {
            "schema": "test.frozen.comparator.synthetic",
            "expected_samples": 2, "expected_arms": 4,
            "qualified": False, "images": self.images,
            "truth_validation": {"schema": "unit-valid", "valid": True},
            "jobs": 2,
        }
        self.calls = []

    def fake_attempt(self, case, dest, name, image, timeout):
        self.assertEqual(timeout, 1800)
        self.assertEqual(name in ("iva", "spades"), True)
        self.assertEqual(image, self.images[name])
        dest.mkdir()
        (dest / "conseq.csv").write_text(
            "region,consensus-percent-cutoff,sequence\nHXB2,MAX,ACTG\n")
        (dest / "scratch").mkdir()
        (dest / "scratch" / "assembly.tmp").write_bytes(b"redundant")
        failed = case[1]["family"] == "minority_30pct" and name == "spades"
        self.calls.append((case[1]["family"], name))
        record = {
            "sha256": image, "score_origin": SCORE_ORIGIN,
            "timing_origin": TIMING_ORIGIN,
            "status": "failed" if failed else "success",
            "exit_code": 3 if failed else 0,
            "seconds": None if failed else 0.7,
            "score": None if failed else 4.0,
            "final_dominant": {
                "source_output": "conseq.csv",
                "conseq_csv_sha256": sha256(
                    (dest / "conseq.csv").read_bytes()).hexdigest(),
            },
        }
        (dest / "execution.json").write_text(json.dumps(record))
        return record

    def execute(self):
        with patch.object(synthetic, "manifest",
                          return_value=(self.frozen, self.cases)), \
             patch.object(synthetic, "TOOLS", ("iva", "spades")), \
             patch.object(synthetic, "attempt", self.fake_attempt), \
             patch.object(synthetic.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=1 << 40)):
            synthetic.run(self.home, self.out, self.home / "images.json", 2)

    def test_arms_checkpointed_and_restored_without_rerunning(self):
        self.execute()
        rows = [json.loads(x) for x in (self.out / "results.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(sum(x["result"]["status"] == "failed" for x in rows), 1)
        for row in rows:
            dest = self.out / row["id"] / row["assembler"]
            self.assertTrue((dest / "conseq.csv").is_file())
            self.assertEqual((dest / "scratch").exists(),
                             row["result"]["status"] == "failed")
        marker = json.loads((self.out / "attempt-finished.json").read_text())
        self.assertEqual(marker["cases"], 2)
        self.assertEqual(marker["arms"], 4)
        self.assertEqual(marker["failed_arms"], 1)
        self.assertEqual(marker["status"], "ATTEMPTED_4_NOT_RELEASE_QUALIFIED")
        self.assertFalse(marker["qualified"])
        self.execute()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(len((self.out / "results.jsonl").read_text().splitlines()), 4)

    def test_changed_frozen_truth_fails_before_reusing_any_arm(self):
        self.execute()
        self.frozen = {**self.frozen,
                       "truth_validation": {"schema": "altered", "valid": True}}
        with self.assertRaisesRegex(ValueError, "changed source/image/cohort"):
            self.execute()
        self.assertEqual(len(self.calls), 4)

    def test_corrupted_final_max_blocks_replay(self):
        self.execute()
        (self.out / "clonal-s000" / "iva" / "conseq.csv").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "final MiCall MAX"):
            self.execute()
        self.assertEqual(len(self.calls), 4)


if __name__ == "__main__":
    unittest.main()
