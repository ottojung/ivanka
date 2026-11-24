"""Narrow fail-closed tests for scoped PX job-temporary reclamation."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assembler_bench import job_temp


class JobTempTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "px-root"
        self.root.mkdir()
        (self.root / ".global-worker.lock").write_text("")
        patch_root = mock.patch.object(job_temp.runtime_cleanup, "ROOT", self.root)
        patch_store = mock.patch.object(job_temp.runtime_cleanup, "STORE",
                                        str(self.root / "store"))
        patch_root.start(); patch_store.start()
        self.addCleanup(patch_root.stop); self.addCleanup(patch_store.stop)
        self.base = job_temp.px_temp_dir(self.root)
        self.base.mkdir()

    def _job(self, ident="job1", pid=None):
        path = job_temp.job_temp_dir(self.root, ident)
        path.mkdir(parents=True)
        (path / "build-scratch.bin").write_bytes(b"rebuildable")
        if pid is not None:
            (path / "pid").write_text(str(pid) + "\n")
        return path

    def test_rejects_foreign_root_and_bad_identifier(self):
        with self.assertRaises(ValueError):
            job_temp.job_temp_dir(self.root, "../escape")
        with mock.patch.object(job_temp.runtime_cleanup, "ROOT", self.root.parent):
            self.assertFalse(job_temp.clean_job_temp(
                self.root, "job1")["removed"])
            self.assertIn("not the dedicated", job_temp.audit_terminal_temp(
                self.root)["reason"])

    def test_removes_only_known_dead_job_temp(self):
        target = self._job()
        unknown = self.base / "mystery-directory"
        unknown.mkdir()
        result = job_temp.clean_job_temp(self.root, "job1")
        self.assertTrue(result["removed"])
        self.assertFalse(target.exists())
        self.assertTrue(unknown.is_dir())

    def test_preserves_live_owner_and_unknown_pid(self):
        target = self._job(pid=os.getpid())
        result = job_temp.clean_job_temp(self.root, "job1")
        self.assertFalse(result["removed"])
        self.assertTrue(target.is_dir())
        (target / "pid").write_text("not-a-pid\n")
        self.assertFalse(job_temp.clean_job_temp(
            self.root, "job1")["removed"])

    def test_preserves_another_worker_lock(self):
        self._job()
        import fcntl
        with (self.root / ".global-worker.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = job_temp.clean_job_temp(self.root, "job1")
        self.assertFalse(result["removed"])
        self.assertIn("another worker", result["reason"])

    def test_preserves_symlink_and_escaping_target(self):
        target = self._job()
        outside = self.root / "outside"
        outside.mkdir()
        (target / "link").symlink_to(outside, target_is_directory=True)
        # The dangerous case is the job target itself being a symlink: it must
        # never be followed or removed as if it were a rebuildable temp dir.
        (target / "link").unlink()
        (target / "build-scratch.bin").unlink()
        target.rmdir()
        target.symlink_to(outside, target_is_directory=True)
        self.assertFalse(job_temp.clean_job_temp(self.root, "job1")["removed"])
        self.assertTrue(outside.is_dir())

    def test_audit_is_readonly_until_armed_and_applies_only_reclaimable(self):
        dead = self._job(ident="dead")
        live = self._job(ident="live", pid=os.getpid())
        unknown = self.base / "unknown"
        unknown.mkdir()
        before = sorted(p.name for p in self.base.iterdir())
        audit = job_temp.audit_terminal_temp(self.root)
        self.assertEqual(audit["applied"], False)
        self.assertEqual(audit["removed"], [])
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), before)
        applied = job_temp.audit_terminal_temp(self.root, apply=True)
        self.assertEqual(applied["removed"], [str(dead)])
        self.assertTrue(dead not in list(self.base.iterdir()))
        self.assertTrue(live.is_dir())
        self.assertTrue(unknown.is_dir())


if __name__ == "__main__":
    unittest.main()
