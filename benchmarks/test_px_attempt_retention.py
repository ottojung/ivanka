"""Adversarial tests for superseded PX scratch retirement."""
import fcntl
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench import px_attempt_retention as retention
from assembler_bench import px_cohort_scheduler as sched


def write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


def record(path, value):
    return write(path, json.dumps(value) + "\n")


class AttemptRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.arm = {
            "tool_id": "skesa", "cohort": "physical", "alias": "PX-R001",
            "input_sha256": {"R1": "a" * 64, "R2": "b" * 64},
            "source_commit": "c" * 40, "adapter_commit": "d" * 40,
            "image_sha256": "e" * 64,
        }
        self.cid = "f" * 64
        self.lease = "skesa-12345"
        self.log = write(self.root / f"run-{self.lease}.log", "unique failure")
        self.digest = sched.sha256_file(self.log)
        self.proof = {"pilot_container_id": self.cid,
                      "fresh_absence_check": True}
        self.report = self.root / f"run-{self.lease}.json"
        self.report_data = {"tool": "skesa", "mode": "pilot", "status": "killed",
                            "reason": "disk_limit", "bound_cid": self.cid,
                            "log_sha256": self.digest, "pilot_cleanup": self.proof}
        record(self.report, self.report_data)
        self.rows = [
            {"schema": "ivanka.worker-lease.v1", "lease": self.lease,
             "state": "active", "cid": self.cid},
            {"schema": "ivanka.worker-lease.v1", "lease": self.lease,
             "state": "released", "cid": self.cid, "proof": self.proof},
        ]
        self.lease_file = self.root / ".worker-lease.jsonl"
        self.write_leases()
        self.lock = write(self.root / ".global-worker.lock", "")
        sched.record_outcome(self.root, self.arm, None, "failure",
                             failure_reason="disk_stop",
                             runner_receipt_sha256=self.digest)
        self.final = write(self.root / "outputs/skesa-PX-R001/conseq.csv",
                           "preserved result")
        sched.record_outcome(self.root, self.arm, self.final, "success", seconds=2)
        self.archive = self.root / "outputs/attempts/skesa-PX-R001.attempt-001"
        self.reads = write(self.archive / "scratch/trimmed1.fastq", "rebuildable")
        self.mapping = write(self.archive / "scratch/unstitched_remap.csv", "rows")
        self.nested = write(self.archive / "scratch/assembly_01/both_mates.fastq",
                            "rebuildable")
        self.unitigs = write(self.archive / "scratch/assembly_01/unitigs.fastq",
                             "native output")
        self.native = write(self.archive / "scratch/assembly_01/contigs.fasta",
                            "native result")
        self.metrics = write(self.archive / "scratch/read_summary.csv", "metrics")
        self.error = write(self.archive / "scratch/assembly_01/error.log", "error")
        self.files = (self.reads, self.mapping, self.nested)
        self.kept = (self.unitigs, self.native, self.metrics, self.error, self.final,
                     self.report, self.log, self.lease_file,
                     sched.receipt_path(self.root, self.arm),
                     sched.attempt_path(self.root, self.arm, 1),
                     sched.attempt_path(self.root, self.arm, 2),
                     sched.index_path(self.root))

    def write_leases(self):
        write(self.lease_file, "".join(json.dumps(r) + "\n" for r in self.rows))

    def run_retire(self, apply=False, dead=True):
        return retention.retire(self.root, apply=apply,
                                dead=lambda root, cid: dead and cid == self.cid)

    def assert_untouched(self):
        self.assertTrue(all(p.exists() for p in self.files))

    def test_dry_run_and_apply_and_replay(self):
        before = {p: p.read_bytes() for p in self.kept}
        plan = self.run_retire()
        self.assertEqual(len(plan["eligible"]), 1)
        self.assertEqual(plan["reclaimed_bytes"], 0)
        self.assert_untouched()
        self.assertFalse((self.archive / retention.SEAL).exists())
        result = self.run_retire(True)
        self.assertGreater(result["reclaimed_bytes"], 0)
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assertEqual(before, {p: p.read_bytes() for p in self.kept})
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)

    def test_live_cid(self):
        self.assertEqual(self.run_retire(True, dead=False)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_lock_busy(self):
        with self.lock.open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaises(BlockingIOError):
                self.run_retire(True)
        self.assert_untouched()

    def test_log_changed(self):
        self.log.write_text("different")
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_duplicate_report(self):
        record(self.root / "run-skesa-999.json", self.report_data)
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_missing_cid_binding(self):
        self.report_data["bound_cid"] = "1" * 64
        record(self.report, self.report_data)
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_no_released_lease(self):
        self.rows.pop()
        self.write_leases()
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_missing_successor_copy(self):
        sched.attempt_path(self.root, self.arm, 2).unlink()
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_successor_output_changed(self):
        self.final.write_text("bad")
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_symlink_never_unlinked(self):
        target = write(self.root / "outside", "protected")
        self.reads.unlink()
        self.reads.symlink_to(target)
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assertEqual(target.read_text(), "protected")
        self.assertTrue(self.reads.is_symlink())

    def test_orphan_not_retired(self):
        self.archive.rename(self.archive.with_name("skesa-PX-R001.orphan-123"))
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)

    def test_seal_conflict(self):
        write(self.archive / retention.SEAL, "{}")
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()


if __name__ == "__main__":
    unittest.main()
