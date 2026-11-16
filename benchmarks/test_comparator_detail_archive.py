"""Crash recovery and complete-evidence tests for lossless MiCall details."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.maintenance import comparator_detail_archive as cold
from benchmarks.maintenance.comparator_detail_storage import (
    ARCHIVE, DETAILS, PROOF, restore_to, sha_file, verify_archive,
)
from benchmarks.expanded.comparator_first import TOOLS
from benchmarks.expanded.comparator_real_first import INVOCATION, PANEL_SHA


class ComparatorDetailArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "results"
        self.root.mkdir()
        self.audit = self.home / "audit"
        self.images = self.home / "images.json"
        self.names = {name: format(i, "x") * 64
                      for i, name in enumerate(TOOLS, start=1)}
        self.tree = "source-tree-sha"
        self.images.write_text(json.dumps(
            {"images": self.names, "source_tree": self.tree}))
        self.frozen = {
            "schema": "ivanka.comparator_first.stitched_counts_real198.v1",
            "qualified": False, "source_commit": cold.EXPECTED_SOURCE,
            "expected_samples": 198, "expected_arms": 1188,
            "images": self.names, "patched_micall_tree": self.tree,
            "image_manifest_sha256": hashlib.sha256(
                self.images.read_bytes()).hexdigest(),
            "original_inputs": {f"sample_{i:03d}": f"paired-{i}"
                                for i in range(198)},
        }
        (self.root / "run_manifest.json").write_text(json.dumps(self.frozen))
        (self.root / "results.jsonl").write_text("")
        manifest_sha = sha_file(self.root / "run_manifest.json")
        images_sha = sha_file(self.images)
        patch_manifest = patch.object(cold, "EXPECTED_MANIFEST_SHA", manifest_sha)
        patch_images = patch.object(cold, "EXPECTED_IMAGES_SHA", images_sha)
        patch_manifest.start()
        patch_images.start()
        self.addCleanup(patch_manifest.stop)
        self.addCleanup(patch_images.stop)
        self.old_mtime = 1000000000

    def arm(self, index, name="iva", state="success"):
        sample = f"sample_{index:03d}"
        folder = self.root / INVOCATION / sample / name
        folder.mkdir(parents=True)
        (folder / "conseq.csv").write_text(
            "region,consensus-percent-cutoff,sequence\nHXB2,MAX,ACTG\n")
        (folder / "nuc.csv").write_bytes(b"protected-score-data")
        maps = folder / "coverage_maps"
        maps.mkdir()
        (maps / "map.png").write_bytes(b"scientific-image")
        if state == "success":
            for detail in DETAILS:
                (folder / detail).write_bytes(
                    (detail + ",real-report\n").encode() * 10000)
                os.utime(folder / detail,
                         ns=(self.old_mtime, self.old_mtime))
        else:
            scratch = folder / "scratch"
            scratch.mkdir()
            (scratch / "failed-diagnostic.fastq").write_bytes(b"unresolved")
        result = {
            "sample": sample, "assembler": name, "status": state,
            "input_sha256": self.frozen["original_inputs"][sample],
            "image_id": self.names[name], "micall": {
                "artifact_dir": str(folder), "image_id": self.names[name],
                "exit_code": 0 if state == "success" else 1,
                "seconds": 14.8, "metrics": {"total_read_depth": 42},
            },
        }
        if state == "success":
            result["final_max"] = {
                "score": 4.0,
                "source_output": "conseq.csv",
                "panel_sha256": PANEL_SHA,
                "sha256": sha_file(folder / "conseq.csv"),
            }
        else:
            result["error"] = "unverified Podman terminal state"
        (folder / "comparator_execution.json").write_text(json.dumps(result))
        with (self.root / "results.jsonl").open("a") as stream:
            stream.write(json.dumps(result, sort_keys=True) + "\n")
        return folder, result

    def execute(self, maximum=10):
        return cold.run(self.root, self.images, self.audit,
                        maximum=maximum)

    def test_success_archives_losslessly_failure_is_unchanged(self):
        good, _ = self.arm(0)
        failed, _ = self.arm(1, "haploflow", "failed")
        before = (self.root / "results.jsonl").read_bytes()
        score = (good / "conseq.csv").read_bytes()
        stats = (good / "nuc.csv").read_bytes()
        maps = (good / "coverage_maps/map.png").read_bytes()
        progress = self.execute()
        self.assertEqual(progress["processed_new_arms"], 1)
        self.assertTrue((good / ARCHIVE).is_file())
        self.assertTrue((good / PROOF).is_file())
        self.assertFalse((good / DETAILS[0]).exists())
        self.assertEqual((good / "conseq.csv").read_bytes(), score)
        self.assertEqual((good / "nuc.csv").read_bytes(), stats)
        self.assertEqual((good / "coverage_maps/map.png").read_bytes(), maps)
        self.assertEqual((self.root / "results.jsonl").read_bytes(), before)
        self.assertEqual((failed / "scratch/failed-diagnostic.fastq").read_bytes(),
                         b"unresolved")
        proof = json.loads((good / PROOF).read_text())
        verify_archive(good / ARCHIVE, proof["details"])
        self.assertLess((good / ARCHIVE).stat().st_size,
                        sum(v["bytes"] for v in proof["details"].values()))
        self.assertEqual(self.execute()["processed_new_arms"], 0)
        self.assertEqual(len((self.audit / "actions.jsonl").read_text().splitlines()), 1)

    def test_restores_all_original_diagnostic_bytes_and_modes(self):
        good, _ = self.arm(0)
        original = {name: (good / name).read_bytes() for name in DETAILS}
        self.execute()
        output = self.home / "restored" / "details"
        self.assertEqual(restore_to(good, output), sorted(DETAILS))
        self.assertEqual({name: (output / name).read_bytes()
                          for name in DETAILS}, original)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            restore_to(good, output)

    def test_crash_after_verified_archive_is_idempotently_recoverable(self):
        good, _ = self.arm(0)
        with patch.object(cold, "retire_originals",
                          side_effect=RuntimeError("simulated crash")):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.execute()
        self.assertTrue((good / ARCHIVE).is_file())
        self.assertTrue((good / PROOF).is_file())
        self.assertTrue((good / DETAILS[0]).is_file())
        self.assertFalse((self.audit / "actions.jsonl").exists())
        self.assertEqual(self.execute()["processed_new_arms"], 1)
        self.assertFalse((good / DETAILS[0]).exists())

    def test_partial_unlink_crash_is_recoverable(self):
        good, _ = self.arm(0)
        path = good / DETAILS[1]
        original_unlink = Path.unlink
        hit = []

        def fail_one(self, *args, **kwargs):
            if self == path and not hit:
                hit.append(True)
                raise RuntimeError("power failure during cleanup")
            return original_unlink(self, *args, **kwargs)

        with patch.object(Path, "unlink", fail_one):
            with self.assertRaisesRegex(RuntimeError, "power failure"):
                self.execute()
        self.assertTrue((good / ARCHIVE).is_file())
        self.assertTrue((good / PROOF).is_file())
        self.assertEqual(self.execute()["processed_new_arms"], 1)
        self.assertTrue(all(not (good / name).exists() for name in DETAILS))

    def test_source_image_and_record_change_fail_closed(self):
        good, _ = self.arm(0)
        self.images.write_text(json.dumps({
            "images": self.names, "source_tree": "corrupt"}))
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.execute()
        self.assertTrue((good / DETAILS[0]).is_file())
        self.images.write_text(json.dumps({
            "images": self.names, "source_tree": self.tree}))
        self.frozen["source_commit"] = "untrusted"
        (self.root / "run_manifest.json").write_text(json.dumps(self.frozen))
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.execute()
        self.assertTrue((good / DETAILS[0]).is_file())

    def test_unjournaled_or_failed_arm_cannot_be_archived(self):
        orphan, _ = self.arm(0)
        (self.root / "results.jsonl").write_text("")
        self.assertEqual(self.execute()["processed_new_arms"], 0)
        self.assertTrue((orphan / DETAILS[0]).exists())

    def test_protected_artifact_mutation_blocks_cleanup(self):
        good, _ = self.arm(0)
        with patch.object(cold, "retire_originals",
                          side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                self.execute()
        (good / "nuc.csv").write_bytes(b"altered!")
        with self.assertRaisesRegex(ValueError, "protected final metrics"):
            self.execute()
        self.assertTrue((good / DETAILS[0]).is_file())

    def test_archived_corruption_prevents_restoration(self):
        good, _ = self.arm(0)
        self.execute()
        (good / ARCHIVE).write_bytes(b"corrupt")
        with self.assertRaises(Exception):
            restore_to(good, self.home / "restored")
        self.assertFalse((self.home / "restored").exists())

    def test_recent_success_is_not_archived(self):
        good, _ = self.arm(0)
        os.utime(good / DETAILS[0], None)
        self.assertEqual(self.execute()["processed_new_arms"], 0)
        self.assertFalse((good / PROOF).exists())

    def test_duplicate_terminal_record_rejected(self):
        good, _ = self.arm(0)
        journal = self.root / "results.jsonl"
        journal.write_bytes(journal.read_bytes() * 2)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.execute()
        self.assertTrue((good / DETAILS[0]).is_file())


if __name__ == "__main__":
    unittest.main()
