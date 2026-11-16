"""Hermetic source-attested cleanup and crash-recovery tests."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.maintenance.prune_completed_pilot_scratch import run

OLD = 1600000000
CUTOFF = 1700000000
FILES = ("execution.json", "conseq.csv", "nuc.csv", "remap_counts.csv",
         "timing.json", "coverage_scores.csv")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PilotScratchPrunerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "old-pilot"
        self.audit = Path(self.tmp.name) / "audit"
        self.root.mkdir()
        self.make_fixture()

    def make_fixture(self, bad=False):
        ids = ("coverage_hole-s000", "equal_strains-s015")
        manifest = {
            "qualified": False, "case_names": list(ids),
            "truth_validation": {"valid": True},
            "source_commit": "frozen-source",
            "images": {"ivanka": "a" * 64},
        }
        (self.root / "pilot-manifest.json").write_text(
            json.dumps(manifest))
        records = []
        for sample in ids:
            arm = self.root / sample / "ivanka"
            maps, scratch = arm / "coverage_maps", arm / "scratch"
            maps.mkdir(parents=True)
            scratch.mkdir()
            (scratch / "remap.csv").write_bytes(b"x" * 4096)
            (maps / "cov.json").write_bytes(b"source-attested-map")
            for filename in FILES:
                if filename != "execution.json":
                    (arm / filename).write_bytes(("original-" + filename).encode())
            state = {
                "status": "failed" if bad else "success",
                "exit_code": 3 if bad else 0,
                "sha256": "a" * 64,
                "final_dominant": {
                    "source_output": "conseq.csv",
                    "conseq_csv_sha256": sha((arm / "conseq.csv").read_bytes()),
                },
            }
            (arm / "execution.json").write_text(json.dumps(state))
            records.append({"id": sample, "ivanka": state})
            os.utime(scratch, (OLD, OLD))
        payload = "".join(json.dumps(record) + "\n" for record in records).encode()
        (self.root / "pilot-results.jsonl").write_bytes(payload)
        marker = {
            "failed_cases": int(bad), "sample_count": 2,
            "results_sha256": sha(payload),
            "pilot_manifest_sha256": sha(
                (self.root / "pilot-manifest.json").read_bytes()),
            "source_commit": "frozen-source",
        }
        (self.root / "pilot-finished.json").write_text(json.dumps(marker))
        for filename in ("pilot-manifest.json", "pilot-results.jsonl",
                         "pilot-finished.json"):
            os.utime(self.root / filename, (OLD, OLD))

    def execute(self, max_new=None):
        return run(self.root, self.audit, 2, CUTOFF, max_new)

    def test_verified_reclaim_and_idempotent_resume(self):
        before = {(a / f).as_posix(): sha((a / f).read_bytes())
                  for a in self.root.glob("*/ivanka")
                  for f in FILES}
        self.assertEqual(self.execute(), (2, 2))
        self.assertEqual(self.execute(), (2, 2))
        for a in self.root.glob("*/ivanka"):
            self.assertFalse((a / "scratch").exists())
            self.assertTrue((a / "coverage_maps/cov.json").exists())
            for f in FILES:
                self.assertEqual(sha((a / f).read_bytes()),
                                 before[(a / f).as_posix()])
        done = json.loads((self.audit / "completed.json").read_text())
        self.assertTrue(done["raw_fastqs_untouched"])
        self.assertTrue(done["coverage_maps_untouched"])
        self.assertEqual(done["logical_bytes_reclaimed"], 8192)

    def test_partial_journal_recovery_does_not_rerun_deleted_case(self):
        self.assertEqual(self.execute(1), (1, 2))
        self.assertFalse((self.audit / "completed.json").exists())
        self.assertEqual(self.execute(), (2, 2))

    def test_recovers_crash_after_delete_before_journal_entry(self):
        self.assertEqual(self.execute(1), (1, 2))
        journal = self.audit / "actions.jsonl"
        journal.unlink()
        self.assertEqual(self.execute(), (2, 2))

    def test_rejects_tampered_final_evidence(self):
        (self.root / "coverage_hole-s000/ivanka/conseq.csv").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "modified successful"):
            self.execute()

    def test_rejects_changed_input_journal(self):
        journal = self.root / "pilot-results.jsonl"
        journal.write_bytes(journal.read_bytes() + b"{}\n")
        os.utime(journal, (OLD, OLD))
        with self.assertRaisesRegex(ValueError, "sealed"):
            self.execute()

    def test_rejects_failed_arms_and_preserves_scratch(self):
        import shutil
        shutil.rmtree(self.root)
        self.root.mkdir()
        self.make_fixture(bad=True)
        with self.assertRaisesRegex(ValueError, "sealed"):
            self.execute()
        self.assertTrue((self.root / "coverage_hole-s000/ivanka/scratch").exists())

    def test_rejects_recent_scratch(self):
        fresh = self.root / "coverage_hole-s000/ivanka/scratch"
        os.utime(fresh, None)
        with self.assertRaisesRegex(ValueError, "too recent"):
            self.execute()

    def test_rejects_symlink_without_deleting_outside(self):
        scratch = self.root / "coverage_hole-s000/ivanka/scratch"
        (scratch / "linked").symlink_to(self.root / "pilot-finished.json")
        os.utime(scratch, (OLD, OLD))
        with self.assertRaisesRegex(ValueError, "links outside"):
            self.execute()
        self.assertTrue((self.root / "pilot-finished.json").exists())

    def test_rejects_modified_coverage_after_verified_cleanup(self):
        self.execute()
        maps = self.root / "equal_strains-s015/ivanka/coverage_maps/cov.json"
        maps.write_bytes(b"modified coverage evidence")
        with self.assertRaisesRegex(ValueError, "proof changed"):
            self.execute()

    def test_rejects_missing_coverage_evidence(self):
        maps = self.root / "coverage_hole-s000/ivanka/coverage_maps/cov.json"
        maps.unlink()
        (maps.parent).rmdir()
        with self.assertRaisesRegex(ValueError, "coverage map"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
