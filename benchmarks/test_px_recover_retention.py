"""Adversarial tests for review-gated unresolved terminal scratch maintenance."""
import fcntl
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_recover_retention as recover
from benchmarks import compressed_tables as codec


def write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


def record(path, value):
    return write(path, json.dumps(value) + "\n")


def body(tag):
    return "".join("%s read-%d chr1 1 60 6M\n" % (tag, n) for n in range(4000))


class RecoverMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        capacity = mock.patch.object(
            recover.os, "statvfs",
            return_value=SimpleNamespace(f_bavail=1 << 50, f_frsize=1))
        capacity.start()
        self.addCleanup(capacity.stop)
        self.arm = {
            "tool_id": "soapdenovo2", "cohort": "physical", "alias": "PX-R046",
            "input_sha256": {"R1": "a" * 64, "R2": "b" * 64},
            "source_commit": "c" * 40, "adapter_commit": "d" * 40,
            "image_sha256": "e" * 64,
        }
        self.cid = "f" * 64
        self.lease = "soapdenovo2-12345"
        self.log = write(self.root / f"run-{self.lease}.log", "disk stop failure")
        self.digest = sched.sha256_file(self.log)
        self.proof = {"pilot_container_id": self.cid,
                      "fresh_absence_check": True}
        self.report = self.root / f"run-{self.lease}.json"
        record(self.report, {"tool": "soapdenovo2", "mode": "pilot",
                             "status": "killed", "reason": "disk_stop",
                             "bound_cid": self.cid,
                             "log_sha256": self.digest,
                             "pilot_cleanup": self.proof})
        self.rows = [
            {"schema": "ivanka.worker-lease.v1", "lease": self.lease,
             "state": "active", "cid": self.cid},
            {"schema": "ivanka.worker-lease.v1", "lease": self.lease,
             "state": "released", "cid": self.cid, "proof": self.proof},
        ]
        self.leases = write(self.root / ".worker-lease.jsonl",
                            "".join(json.dumps(r) + "\n" for r in self.rows))
        write(self.root / ".global-worker.lock", "")
        sched.record_outcome(self.root, self.arm, None, "failure",
                             failure_reason="disk_stop",
                             runner_receipt_sha256=self.digest)
        # An unresolved first attempt has no superseding write to preserve it.
        self.original = write(
            sched.attempt_path(self.root, self.arm, 1),
            sched.receipt_path(self.root, self.arm).read_text())
        self.archive = (self.root / "outputs" / "attempts" /
                        "soapdenovo2-PX-R046.attempt-001")
        self.reads = write(self.archive / "scratch/temp.sam", body("sam"))
        self.mates = write(self.archive / "scratch/assembly_01/both_mates.fastq",
                           body("mates"))
        self.metrics = write(self.archive / "scratch/read_summary.csv", "metrics")
        self.native = write(self.archive / "scratch/assembly_01/contigs.fasta",
                            "native result")
        self.error = write(self.archive / "scratch/assembly_01/error.log", "error")
        self.files = (self.reads, self.mates)
        self.originals = {p: p.read_bytes() for p in self.files}
        self.kept = (self.metrics, self.native, self.error, self.log,
                     self.report, self.leases, self.archive.parent,
                     sched.receipt_path(self.root, self.arm),
                     sched.attempt_path(self.root, self.arm, 1))

    def review(self, *, approved=True, module=None, attempts=None,
               reviewer="independent-review-test"):
        data = {"approved": approved,
                "module_sha256": module or recover._module_sha256(),
                "attempts": attempts or [self.archive.name],
                "reviewer": reviewer}
        return record(self.root / recover.REVIEW_NAME, data)

    def run_recover(self, *, apply=False, dead=True):
        return recover.recover(
            self.root, apply=apply,
            dead=lambda root, cid: dead and cid == self.cid)

    def run_apply(self, review, dead=True):
        return recover.recover(
            self.root, apply=True, review=review,
            dead=lambda root, cid: dead and cid == self.cid)

    def run_restore(self, dead=True):
        return recover.restore(
            self.root, only=self.archive.name,
            dead=lambda root, cid: dead and cid == self.cid)

    def test_dry_run_is_read_only(self):
        before = {p: p.read_bytes() for p in self.files}
        plan = self.run_recover()
        self.assertEqual(len(plan["eligible"]), 1)
        self.assertEqual(plan["reclaimed_bytes"], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in self.files})
        self.assertFalse((self.archive / recover.retention.SEAL).exists())

    def test_apply_requires_source_bound_review(self):
        with self.assertRaises(ValueError):
            recover.recover(self.root, apply=True)
        self.review(module="0" * 64)
        result = self.run_apply(self.root / recover.REVIEW_NAME)
        self.assertTrue(result["skipped"])
        self.assertEqual({p: p.read_bytes() for p in self.files}, self.originals)

    def test_apply_is_lossless_idempotent_and_preserves_evidence(self):
        review = self.review()
        kept_before = {p: p.read_bytes() for p in self.kept if p.is_file()}
        result = self.run_apply(review)
        self.assertEqual(result["skipped"], [])
        self.assertEqual(len(result["applied"]), 1)
        self.assertGreater(result["applied"][0]["reclaimed_bytes"], 0)
        for path, original in self.originals.items():
            self.assertFalse(path.exists())
            frame = path.with_name(path.name + codec.ZST_SUFFIX)
            meta = path.with_name(path.name + codec.META_SUFFIX)
            self.assertTrue(frame.is_file() and meta.is_file())
            proof = codec.load_meta(meta, format=codec.SCRATCH_FORMAT)
            self.assertEqual((proof["original_sha256"], proof["original_size"]),
                             (hashlib.sha256(original).hexdigest(),
                              len(original)))
            self.assertEqual(codec.logical_digest(
                path, format=codec.SCRATCH_FORMAT),
                (proof["original_sha256"], proof["original_size"]))
        self.assertEqual(kept_before,
                         {p: p.read_bytes() for p in self.kept if p.is_file()})
        seal_path = self.archive / recover.retention.SEAL
        self.assertEqual(sched.sha256_file(seal_path),
                         result["applied"][0]["seal_sha256"])
        replay = self.run_apply(review)
        self.assertEqual(replay["reclaimed_bytes"], 0)
        self.assertEqual(replay["applied"], [])
        self.assertEqual(len(replay["already_archived"]), 1)

    def test_restore_roundtrip(self):
        self.run_apply(self.review())
        result = self.run_restore()
        self.assertEqual(result["skipped"], [])
        self.assertEqual(len(result["restored"]), len(self.files))
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + codec.ZST_SUFFIX).exists())
            self.assertFalse(path.with_name(path.name + codec.META_SUFFIX).exists())

    def test_below_benchmark_reserve_still_applies(self):
        # The benchmark reserve is untouched; only the separate maintenance
        # temporary floor governs this bounded frame.
        self.assertEqual(recover.MIN_WORKSPACE_FREE_BYTES, 32 * 1024**3)
        with mock.patch.object(recover.os, "statvfs", return_value=SimpleNamespace(
                f_bavail=512 * 1024**2, f_frsize=1)):
            result = self.run_apply(self.review())
        self.assertEqual(result["skipped"], [])
        self.assertGreater(result["reclaimed_bytes"], 0)
        self.assertFalse(self.reads.exists())

    def test_no_headroom_fails_closed(self):
        with mock.patch.object(recover.os, "statvfs", return_value=SimpleNamespace(
                f_bavail=1, f_frsize=1)):
            result = self.run_apply(self.review())
        self.assertTrue(result["skipped"])
        self.assertTrue(self.reads.exists())

    def test_contention_fails_closed(self):
        lock = (self.root / ".global-worker.lock").open("r+")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(OSError):
                self.run_apply(self.review())
        finally:
            lock.close()
        self.assertTrue(self.reads.exists())

    def test_resolved_superseding_attempt_refused(self):
        final = write(self.root / "outputs" / "soapdenovo2-PX-R046" /
                      sched.MAX_ARTIFACT, "final")
        sched.record_outcome(self.root, self.arm, final, "success", seconds=2)
        result = self.run_recover()
        self.assertEqual(result["eligible"], [])
        self.assertTrue(result["skipped"])

    def test_partial_pair_fails_closed(self):
        self.run_apply(self.review())
        meta = self.reads.with_name(self.reads.name + codec.META_SUFFIX)
        meta.unlink()
        result = self.run_apply(self.review())
        self.assertTrue(result["skipped"])

    def test_symlink_escape_refused(self):
        outside = write(self.root / "outside.sam", "secret")
        self.reads.unlink()
        self.reads.symlink_to(outside)
        result = self.run_recover()
        self.assertEqual(result["eligible"], [])
        self.assertTrue(result["skipped"])
        self.assertTrue(outside.exists())

    def test_incompressible_scratch_refused(self):
        self.reads.write_bytes(os.urandom(1 << 20))
        result = self.run_apply(self.review())
        self.assertTrue(result["skipped"])
        self.assertTrue(self.reads.exists())

    def test_mixed_state_resume_completes_without_data_loss(self):
        review = self.review()
        archive_one = recover._archive_one

        def fail_after_first(path, item, root):
            if path.name == "temp.sam":
                raise ValueError("injected mid-loop failure")
            return archive_one(path, item, root)

        with mock.patch.object(recover, "_archive_one", side_effect=fail_after_first):
            interrupted = self.run_apply(review)
        self.assertEqual(interrupted["applied"], [])
        self.assertEqual(len(interrupted["skipped"]), 1)
        self.assertIn("injected mid-loop failure", interrupted["skipped"][0]["reason"])
        self.assertFalse(self.mates.exists())
        self.assertTrue(self.reads.exists())

        retry = self.run_apply(review)
        self.assertEqual(retry["skipped"], [])
        self.assertEqual(len(retry["applied"]), 1)
        self.assertGreater(retry["applied"][0]["reclaimed_bytes"], 0)
        for path, original in self.originals.items():
            self.assertFalse(path.exists())
            self.assertEqual(
                codec.logical_digest(path, format=codec.SCRATCH_FORMAT),
                (hashlib.sha256(original).hexdigest(), len(original)))
        self.assertEqual(len(self.run_recover()["already_archived"]), 1)

    def test_review_rejects_blanket_attempts(self):
        result = self.run_apply(self.review(attempts=["*"]))
        self.assertTrue(result["skipped"])
        self.assertIn("explicit attempts", result["skipped"][0]["reason"])
        self.assertEqual({p: p.read_bytes() for p in self.files}, self.originals)

    def test_review_requires_named_reviewer(self):
        result = self.run_apply(self.review(reviewer=None))
        self.assertTrue(result["skipped"])
        self.assertIn("name a reviewer", result["skipped"][0]["reason"])
        self.assertEqual({p: p.read_bytes() for p in self.files}, self.originals)

    def test_review_requires_absolute_path(self):
        relative = os.path.relpath(self.review(), Path.cwd())
        result = self.run_apply(relative)
        self.assertTrue(result["skipped"])
        self.assertIn("absolute", result["skipped"][0]["reason"])
        self.assertEqual({p: p.read_bytes() for p in self.files}, self.originals)


if __name__ == "__main__":
    unittest.main()
