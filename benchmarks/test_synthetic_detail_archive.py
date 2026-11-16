"""Synthetic400 comparator detail preservation, provenance and crash safety."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.maintenance import synthetic_detail_archive as cold
from benchmarks.maintenance.comparator_detail_storage import (
    ARCHIVE, DETAILS, PROOF, restore_to, sha_file, verify_archive,
)
from benchmarks.expanded.comparator_first import TOOLS, verify_record
from benchmarks.expanded.micall_checkpoint import identity
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from benchmarks.expanded.micall_synthetic_constants import TIMING_ORIGIN


class SyntheticDetailArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "results"
        self.data = self.home / "HXB2-cohort"
        self.audit = self.home / "archive_audit"
        self.images = self.home / "images.json"
        self.preflight = self.home / "preflight.json"
        self.root.mkdir()
        self.data.mkdir()
        self.image_ids = {name: format(i, "x") * 64
                          for i, name in enumerate(TOOLS, start=1)}
        self.images.write_text(json.dumps({
            "images": self.image_ids, "source_tree": "same-source-tree"}))
        self.truth = {"valid": True, "cohort_sha256": "attested-cohort"}
        self.ids = [f"sample{i:03d}" for i in range(400)]
        entries = []
        for sample in self.ids:
            entry = {"id": sample, "sha256": {
                "reads/R1.fastq.gz": sample+"-r1",
                "reads/R2.fastq.gz": sample+"-r2",
            }}
            entries.append(entry)
        cohort = {"schema": "ivanka.expanded.cohort.hxb2.v2",
                  "samples": 400, "cases": entries}
        (self.data / "cohort.json").write_text(json.dumps(cohort))
        self.entries = {x["id"]: x for x in entries}
        self.frozen = {
            "schema": "ivanka.comparator_first.stitched_counts_400.v1",
            "qualified": False, "source_commit": cold.SOURCE,
            "expected_samples": 400, "expected_arms": 2400,
            "truth_validation": self.truth,
            "images": self.image_ids, "patched_micall_tree": "same-source-tree",
            "image_manifest_sha256": sha_file(self.images),
            "original_cohort_manifest_sha256": sha_file(
                self.data / "cohort.json"),
        }
        (self.root / "run_manifest.json").write_text(
            json.dumps(self.frozen))
        (self.root / "results.jsonl").write_text("")
        self.preflight.write_text(json.dumps({
            "schema": "original HXB2 truth preflight", "qualified": False,
            "sample_ids": self.ids, "manifest": self.frozen,
        }))
        for name, p in [("PREFLIGHT_SHA", self.preflight),
                        ("IMAGES_SHA", self.images)]:
            effect = patch.object(cold, name, sha_file(p))
            effect.start()
            self.addCleanup(effect.stop)

    def arm(self, sample="sample000", tool="iva", failed=False):
        source = self.data / sample
        source.mkdir(exist_ok=True)
        metadata = {"family": "minority_30pct",
                    "sha256": self.entries[sample]["sha256"]}
        (source / "manifest.json").write_text(json.dumps(metadata))
        folder = self.root / sample / tool
        folder.mkdir(parents=True)
        (folder / "conseq.csv").write_text(
            "region,consensus-percent-cutoff,sequence\nHXB2,MAX,ACTG\n")
        (folder / "nuc.csv").write_bytes(b"original nuc q15 metrics")
        (folder / "coverage_maps").mkdir()
        (folder / "coverage_maps" / "map.png").write_bytes(
            b"original exact coverage map")
        if not failed:
            for detail in DETAILS:
                (folder / detail).write_bytes(
                    (detail+",scientific\n").encode()*10000)
                os.utime(folder / detail, ns=(1000000000, 1000000000))
        else:
            (folder / "scratch").mkdir()
            (folder / "scratch" / "error.txt").write_text("unverified failure")
        result = {
            "sha256": self.image_ids[tool],
            "score_origin": SCORE_ORIGIN, "timing_origin": TIMING_ORIGIN,
            "status": "failed" if failed else "success",
            "exit_code": 137 if failed else 0,
            "seconds": 9.3, "score": None if failed else 4.0,
            "final_dominant": {
                "source_output": "conseq.csv",
                "conseq_csv_sha256": sha_file(folder / "conseq.csv"),
            },
        }
        (folder / "execution.json").write_text(json.dumps(result))
        record = {**identity(sample, metadata, self.truth),
                  "assembler": tool, "result": result}
        with (self.root / "results.jsonl").open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True)+"\n")
        return folder, record

    def execute(self, count=10):
        return cold.run(self.root, self.data, self.images,
                        self.preflight, self.audit, maximum=count)

    def test_success_is_archived_and_failed_evidence_is_not_touched(self):
        success, row = self.arm()
        failed, _ = self.arm("sample001", "haploflow", failed=True)
        journal = (self.root / "results.jsonl").read_bytes()
        final = (success / "conseq.csv").read_bytes()
        nuc = (success / "nuc.csv").read_bytes()
        maps = (success / "coverage_maps/map.png").read_bytes()
        self.assertEqual(self.execute()["new_arms"], 1)
        self.assertTrue((success / ARCHIVE).is_file())
        self.assertFalse((success / DETAILS[0]).exists())
        self.assertEqual((success / "conseq.csv").read_bytes(), final)
        self.assertEqual((success / "nuc.csv").read_bytes(), nuc)
        self.assertEqual((success / "coverage_maps/map.png").read_bytes(), maps)
        self.assertEqual((self.root / "results.jsonl").read_bytes(), journal)
        self.assertEqual((failed / "scratch/error.txt").read_text(),
                         "unverified failure")
        self.assertEqual(self.execute()["new_arms"], 0)
        proof = json.loads((success / PROOF).read_text())
        verify_archive(success / ARCHIVE, proof["details"])
        fields = {key: row[key] for key in (
            "id", "cohort", "family", "truth_validation", "input_sha256")}
        verify_record(row, fields, self.root, self.image_ids)

    def test_recovery_and_restore_exact_bytes(self):
        success, _ = self.arm()
        original = {name: (success / name).read_bytes() for name in DETAILS}
        with patch.object(cold, "retire_originals",
                          side_effect=RuntimeError("simulated crash")):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.execute()
        self.assertTrue((success / ARCHIVE).is_file())
        self.assertTrue((success / DETAILS[0]).is_file())
        self.assertEqual(self.execute()["new_arms"], 1)
        restore = self.home / "separate-restoration"
        self.assertEqual(restore_to(success, restore), sorted(DETAILS))
        self.assertEqual({name: (restore / name).read_bytes()
                          for name in DETAILS}, original)

    def test_source_and_image_manifest_changes_rejected(self):
        success, _ = self.arm()
        self.frozen["source_commit"] = "untrusted"
        (self.root / "run_manifest.json").write_text(json.dumps(self.frozen))
        with self.assertRaisesRegex(ValueError, "differs from preflight"):
            self.execute()
        self.assertTrue((success / DETAILS[0]).exists())
        (self.root / "run_manifest.json").write_text(json.dumps({
            **self.frozen, "source_commit": cold.SOURCE}))
        self.images.write_text(json.dumps({
            "images": self.image_ids, "source_tree": "changed"}))
        with self.assertRaisesRegex(ValueError, "prelaunch proof"):
            self.execute()

    def test_original_case_manifest_change_rejected(self):
        success, _ = self.arm()
        (self.data / "sample000" / "manifest.json").write_text(
            '{"sha256":{"reads/R1.fastq.gz":"changed"}}')
        with self.assertRaisesRegex(ValueError, "altered original"):
            self.execute()
        self.assertTrue((success / DETAILS[0]).exists())

    def test_corrupt_final_micall_max_blocks_archive(self):
        success, _ = self.arm()
        (success / "conseq.csv").write_text("changed original score")
        with self.assertRaisesRegex(ValueError, "cached final"):
            self.execute()
        self.assertTrue((success / DETAILS[0]).exists())

    def test_partial_journal_and_duplicate_rejected(self):
        success, row = self.arm()
        journal = self.root / "results.jsonl"
        raw = journal.read_bytes()
        journal.write_bytes(raw + b"{")
        with self.assertRaisesRegex(ValueError, "incomplete synthetic"):
            self.execute()
        journal.write_bytes(raw * 2)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.execute()
        self.assertTrue((success / DETAILS[0]).exists())

    def test_largest_scientific_detail_first(self):
        small, _ = self.arm("sample000")
        big, _ = self.arm("sample001")
        (big / DETAILS[0]).write_bytes(b"B" * 3_000_000)
        os.utime(big / DETAILS[0], ns=(1000000000, 1000000000))
        self.assertEqual(self.execute(count=1)["new_arms"], 1)
        self.assertFalse((big / DETAILS[0]).exists())
        self.assertTrue((small / DETAILS[0]).exists())

    def test_archived_corruption_cannot_be_silently_restored(self):
        success, _ = self.arm()
        self.execute()
        (success / ARCHIVE).write_bytes(b"tampered archive")
        with self.assertRaises(Exception):
            restore_to(success, self.home / "restored")
        self.assertFalse((self.home / "restored").exists())


if __name__ == "__main__":
    unittest.main()
