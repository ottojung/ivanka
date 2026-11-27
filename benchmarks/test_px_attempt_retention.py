"""Adversarial tests for superseded PX scratch archival and retirement."""
import fcntl
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from assembler_bench import px_attempt_retention as retention
from assembler_bench import px_cohort_scheduler as sched
from benchmarks import compressed_tables as codec


def write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


def record(path, value):
    return write(path, json.dumps(value) + "\n")


def body(tag):
    """A reproducible, well-compressible read-level scratch body."""
    return "".join("%s read-%d chr1 1 60 6M\n" % (tag, n) for n in range(2000))


class AttemptRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        capacity = mock.patch.object(
            retention.os, "statvfs",
            return_value=SimpleNamespace(f_bavail=1 << 50, f_frsize=1))
        capacity.start()
        self.addCleanup(capacity.stop)
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
        self.reads = write(self.archive / "scratch/trimmed1.fastq", body("fastq"))
        self.mapping = write(self.archive / "scratch/unstitched_remap.csv", body("csv"))
        self.nested = write(self.archive / "scratch/assembly_01/both_mates.fastq",
                            body("mates"))
        self.unitigs = write(self.archive / "scratch/assembly_01/unitigs.fastq",
                             "native output")
        self.native = write(self.archive / "scratch/assembly_01/contigs.fasta",
                            "native result")
        self.metrics = write(self.archive / "scratch/read_summary.csv", "metrics")
        self.error = write(self.archive / "scratch/assembly_01/error.log", "error")
        self.files = (self.reads, self.mapping, self.nested)
        self.originals = {p: p.read_bytes() for p in self.files}
        self.kept = (self.unitigs, self.native, self.metrics, self.error, self.final,
                     self.report, self.log, self.lease_file,
                     sched.receipt_path(self.root, self.arm),
                     sched.attempt_path(self.root, self.arm, 1),
                     sched.attempt_path(self.root, self.arm, 2),
                     sched.index_path(self.root))

    def write_leases(self):
        write(self.lease_file, "".join(json.dumps(r) + "\n" for r in self.rows))

    def run_retire(self, apply=False, dead=True, mode=retention.ARCHIVE_MODE):
        return retention.retire(self.root, apply=apply,
                                dead=lambda root, cid: dead and cid == self.cid,
                                mode=mode)

    def run_restore(self, dead=True):
        return retention.restore(self.root, only=self.archive.name,
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
        for path, original in self.originals.items():
            self.assertFalse(path.exists())
            frame = path.with_name(path.name + codec.ZST_SUFFIX)
            meta = path.with_name(path.name + codec.META_SUFFIX)
            self.assertTrue(frame.is_file())
            self.assertTrue(meta.is_file())
            proof = codec.load_meta(meta, format=codec.SCRATCH_FORMAT)
            self.assertEqual((proof["original_sha256"], proof["original_size"]),
                             (hashlib.sha256(original).hexdigest(),
                              len(original)))
            self.assertEqual(codec.logical_digest(
                path, format=codec.SCRATCH_FORMAT),
                (proof["original_sha256"], proof["original_size"]))
        self.assertEqual(before, {p: p.read_bytes() for p in self.kept})
        replay = self.run_retire(True)
        self.assertEqual(replay["reclaimed_bytes"], 0)
        self.assertEqual(replay["eligible"], [])

    def test_restore_roundtrip(self):
        self.run_retire(True)
        result = self.run_restore()
        self.assertEqual(result["skipped"], [])
        self.assertEqual(len(result["restored"]), len(self.files))
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + codec.ZST_SUFFIX).exists())
            self.assertFalse(path.with_name(path.name + codec.META_SUFFIX).exists())
        self.run_retire(True)

    def test_interrupted_install_resumes(self):
        """A proven pair left beside its source is finished, never guessed."""
        before = {p: p.read_bytes() for p in self.kept}
        frame, proof = codec.prepare_scratch(self.reads)
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        meta.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")
        os.replace(frame, self.reads.with_name(
            self.reads.name + codec.ZST_SUFFIX))
        result = self.run_retire(True)
        self.assertEqual(result["skipped"], [])
        self.assertFalse(self.reads.exists())
        self.assertEqual(codec.logical_digest(
            self.reads, format=codec.SCRATCH_FORMAT),
            (proof["original_sha256"], proof["original_size"]))
        self.assertEqual(before, {p: p.read_bytes() for p in self.kept})
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)

    def test_crash_after_frame_rename_before_proof_is_repaired(self):
        """Simulate the os.replace window: plain intact, frame published."""
        before = {p: p.read_bytes() for p in self.kept}
        frame, proof = codec.prepare_scratch(self.reads)
        os.replace(frame, self.reads.with_name(
            self.reads.name + codec.ZST_SUFFIX))
        result = self.run_retire(True)
        self.assertEqual(result["skipped"], [])
        self.assertFalse(self.reads.exists())
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        self.assertTrue(meta.is_file())
        self.assertEqual(codec.logical_digest(
            self.reads, format=codec.SCRATCH_FORMAT),
            (proof["original_sha256"], proof["original_size"]))
        self.assertEqual(before, {p: p.read_bytes() for p in self.kept})

    def test_crash_after_proof_before_frame_is_repaired(self):
        _, proof = codec.prepare_scratch(self.reads)
        self.reads.with_name(self.reads.name + codec.META_SUFFIX).write_text(
            json.dumps(proof, sort_keys=True, indent=2) + "\n")
        result = self.run_retire(True)
        self.assertEqual(result["skipped"], [])
        self.assertFalse(self.reads.exists())
        self.assertTrue(self.reads.with_name(
            self.reads.name + codec.ZST_SUFFIX).is_file())
        self.assertEqual(codec.logical_digest(
            self.reads, format=codec.SCRATCH_FORMAT),
            (proof["original_sha256"], proof["original_size"]))

    def test_incomplete_pair_without_plain_fails_closed(self):
        self.run_retire(True)
        self.reads.with_name(self.reads.name + codec.META_SUFFIX).unlink()
        result = self.run_retire(True)
        self.assertTrue(result["skipped"])
        self.assertFalse(self.reads.exists())
        self.assertFalse(self.reads.with_name(
            self.reads.name + codec.META_SUFFIX).exists())

    def test_truncated_staged_frame_is_refused(self):
        frame, proof = codec.prepare_scratch(self.reads)
        stored = self.reads.with_name(self.reads.name + codec.ZST_SUFFIX)
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        stored.write_bytes(frame.read_bytes()[:-4])
        meta.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")
        codec.discard_scratch_frame(frame)
        result = self.run_retire(True)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertTrue(result["skipped"])
        self.assertEqual(self.reads.read_bytes(), self.originals[self.reads])

    def test_lease_gate_requires_prior_active(self):
        self.rows[:] = [{"schema": "ivanka.worker-lease.v1",
                         "lease": self.lease, "state": "released",
                         "cid": self.cid, "proof": self.proof}]
        self.write_leases()
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()

    def test_delete_mode(self):
        before = {p: p.read_bytes() for p in self.kept}
        result = self.run_retire(True, mode=retention.DELETE_MODE)
        self.assertGreater(result["reclaimed_bytes"], 0)
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assertFalse(self.reads.with_name(
            self.reads.name + codec.ZST_SUFFIX).exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.kept})

    def test_seal_mode_is_exclusive(self):
        self.run_retire(True)
        result = self.run_retire(True, mode=retention.DELETE_MODE)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertEqual(result["eligible"], [])
        self.assertTrue(self.reads.with_name(
            self.reads.name + codec.ZST_SUFFIX).is_file())

    def test_corrupt_proof_blocks_restore(self):
        self.run_retire(True)
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        proof = json.loads(meta.read_text())
        proof["compressed_sha256"] = "0" * 64
        meta.write_text(json.dumps(proof) + "\n")
        result = self.run_restore()
        self.assertTrue(result["skipped"])
        self.assertFalse(self.reads.exists())

    def test_missing_proof_blocks_restore(self):
        self.run_retire(True)
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        meta.unlink()
        result = self.run_restore()
        self.assertTrue(result["skipped"])
        self.assertFalse(self.reads.exists())

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

    def test_restore_requires_dead_cid(self):
        self.run_retire(True)
        result = self.run_restore(dead=False)
        self.assertTrue(result["skipped"])
        self.assertFalse(self.reads.exists())

    def test_restore_requires_headroom(self):
        self.run_retire(True)
        with mock.patch.object(retention.os, "statvfs", return_value=SimpleNamespace(
                f_bavail=1, f_frsize=1)):
            result = self.run_restore()
        self.assertTrue(result["skipped"])
        self.assertFalse(self.reads.exists())

    def test_archive_preflight_refuses_tight_capacity(self):
        with mock.patch.object(retention.os, "statvfs", return_value=SimpleNamespace(
                f_bavail=1, f_frsize=1)):
            result = self.run_retire(True)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertTrue(result["skipped"])
        self.assert_untouched()
        self.assertEqual(list(self.archive.rglob("*.tmp.*")), [])
        self.assertEqual(list(self.archive.rglob("*.zst")), [])

    def test_delete_mode_is_idempotent(self):
        first = self.run_retire(True, mode=retention.DELETE_MODE)
        self.assertGreater(first["reclaimed_bytes"], 0)
        second = self.run_retire(True, mode=retention.DELETE_MODE)
        self.assertEqual(second["reclaimed_bytes"], 0)
        self.assertEqual(second["skipped"], [])
        self.assertTrue(all(not p.exists() for p in self.files))

    def test_archived_variant_symlink_refused(self):
        self.run_retire(True)
        frame = self.reads.with_name(self.reads.name + codec.ZST_SUFFIX)
        target = self.root / "outside.zst"
        target.write_bytes(frame.read_bytes())
        frame.unlink()
        frame.symlink_to(target)
        result = self.run_retire(True)
        self.assertTrue(result["skipped"])

    def test_archived_plain_absent_verified_against_seal(self):
        self.run_retire(True)
        # plain is absent, pair present - replay should verify against seal
        result = self.run_retire(True)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertEqual(result["skipped"], [])

    def test_seal_conflict(self):
        write(self.archive / retention.SEAL, "{}")
        self.assertEqual(self.run_retire(True)["reclaimed_bytes"], 0)
        self.assert_untouched()


if __name__ == "__main__":
    unittest.main()
