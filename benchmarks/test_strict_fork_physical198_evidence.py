"""Fast tampering tests for retained MiCall physical input and output evidence."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.expanded.strict_fork_physical198_evidence import (
    check_retained_arm, digest, sample_provenance,
)

SAMPLE = "synthetic-sample"
IMAGES = {"iva": "a" * 64, "ivanka": "b" * 64}
HXB2 = hashlib.sha256(b">hxb2\nACGT\n").hexdigest()


class RetainedSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.dataset = self.root / "dataset"
        original = self.dataset / "samples" / SAMPLE
        original.mkdir(parents=True)
        self.fastqs = [original / f"{SAMPLE}_L001_R{i}_001.fastq.gz"
                       for i in (1, 2)]
        for index, f in enumerate(self.fastqs):
            f.write_bytes(bytes([index + 1]) * 32)
        self.row = {"sample": SAMPLE, "micall_project_code": "HIV"}
        self.record = {
            "sample": SAMPLE, "hxb2_sha256": HXB2,
            "sample_time_limit_seconds": 1800, "invocation": "invocation",
            "provenance": {
                "iva_image_id": IMAGES["iva"], "hxb2_sha256": HXB2,
                "all_projects": True,
                "fastq_sha256": [digest(f) for f in self.fastqs],
                "micall_project_code": "HIV",
            },
        }
        self.folder = self.root / "invocation" / SAMPLE / "iva"
        self.folder.mkdir(parents=True)
        self.conseq = self.folder / "conseq.csv"
        with self.conseq.open("w", newline="") as file:
            out = csv.DictWriter(file, fieldnames=["consensus-percent-cutoff", "sequence"])
            out.writeheader()
            out.writerow({"consensus-percent-cutoff": "MAX", "sequence": "ACGT"})
        self.timer = self.folder / "micall_internal_timing.json"
        self.timer.write_text(json.dumps(
            {"exit_code": 0, "seconds": 1.5, "timing_origin":
             "micall_in_container_monotonic_v1"}))
        self.record["iva"] = {
            "image": IMAGES["iva"], "image_id": IMAGES["iva"],
            "artifact_dir": str(self.folder), "seconds": 1.5,
            "metrics": {"num_final_max_conseqs": 1,
                        "outputs": {"conseq.csv": {"exists": True, "rows": 1,
                                                 "sha256": digest(self.conseq)}}},
        }

    def tearDown(self):
        self.directory.cleanup()

    def test_accepts_exact_original_and_final_data(self):
        sample_provenance(SAMPLE, self.row, self.record, self.dataset, IMAGES,
                          HXB2)
        check_retained_arm(SAMPLE, self.record, "iva", self.root, IMAGES["iva"])

    def test_reject_changed_original_pair_bytes(self):
        self.fastqs[1].write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "FASTQ bytes"):
            sample_provenance(SAMPLE, self.row, self.record, self.dataset,
                              IMAGES, HXB2)

    def test_reject_substituted_project_or_cache(self):
        self.record["provenance"]["micall_project_code"] = "not-original"
        with self.assertRaisesRegex(ValueError, "provenance"):
            sample_provenance(SAMPLE, self.row, self.record, self.dataset,
                              IMAGES, HXB2)
        self.record["provenance"]["micall_project_code"] = "HIV"
        self.record["iva_baseline_reused"] = False
        with self.assertRaisesRegex(ValueError, "non-fresh"):
            sample_provenance(SAMPLE, self.row, self.record, self.dataset,
                              IMAGES, HXB2)

    def test_reject_changed_final_consensus(self):
        self.conseq.write_text("consensus-percent-cutoff,sequence\nMAX,TTTT\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            check_retained_arm(SAMPLE, self.record, "iva", self.root,
                               IMAGES["iva"])

    def test_reject_changed_timing(self):
        self.timer.write_text(json.dumps({
            "exit_code": 0, "seconds": 1.6,
            "timing_origin": "micall_in_container_monotonic_v1"}))
        with self.assertRaisesRegex(ValueError, "timing"):
            check_retained_arm(SAMPLE, self.record, "iva", self.root,
                               IMAGES["iva"])

    def test_reject_wrong_artifact_dir(self):
        self.record["iva"]["artifact_dir"] = str(self.root)
        with self.assertRaisesRegex(ValueError, "directory"):
            check_retained_arm(SAMPLE, self.record, "iva", self.root,
                               IMAGES["iva"])


if __name__ == "__main__":
    unittest.main()
