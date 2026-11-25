"""Single-worker real process-group supervision and immutable storage checks."""
import copy
import fcntl
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_runtime.launch import operate

REG = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.policy = copy.deepcopy(checked(REG))
        self.policy["policy"]["dedicated_podman_storage_conf"] = str(self.root / "storage.conf")
        self.policy["policy"]["dedicated_image_store_root"] = str(self.store)
        (self.root / "storage.conf").write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "'+str(self.store / 'store')+
            '"\nrunroot = "'+str(self.store / 'run')+'"\n')
        base = {"schema": "ivanka.exploratory.storage-baseline.v1",
                "root": str(self.root), "image_store": str(self.store),
                "workspace": str(self.root), "base_store_bytes": 0,
                "frozen_manifest_sha256": self.policy["policy"]["frozen_seven_manifest_sha256"],
                "active_job": None}
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps(base))
        self.policy["storage_baseline_sha256"] = hashlib.sha256(
            self.baseline.read_bytes()).hexdigest()
        self.config = patch("assembler_bench.exploratory_runtime.setup.checked",
                            return_value=self.policy)
        self.available = patch("assembler_bench.exploratory_space.available",
                               return_value=100 * 1024**3)
        self.config.start()
        self.available.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.available.stop)

    def run_job(self, mode="build", argv=None):
        return operate(REG, self.baseline, "skesa", mode,
                       argv or [sys.executable, "-c", "print('hello')"], 1024**3)

    def test_real_foreground_process_and_hashed_log(self):
        result = self.run_job()
        self.assertEqual(result["status"], "finished")
        records = list(self.root.glob("run-*.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text()), result)
        self.assertIn("log_sha256", result)

    def test_child_temporaries_are_redirected_into_metered_directory(self):
        argv = [sys.executable, "-c",
                ("import os, pathlib; p = pathlib.Path(os.environ['TMPDIR']); "
                 "(p / 'px-tmp-probe').write_text(str(p))")]
        result = self.run_job(argv=argv)
        self.assertEqual(result["status"], "finished")
        metered = (self.root / "tmp").resolve()
        probes = list((self.root / "tmp").glob("job-*/px-tmp-probe"))
        self.assertEqual(len(probes), 1)
        probe = probes[0]
        self.assertTrue(probe.is_file())
        # The per-job TMPDIR stays inside the metered tree so disk accounting
        # sees every byte; scoped teardown may remove it after this assertion.
        self.assertTrue(probe.parent.resolve().is_relative_to(metered))
        self.assertEqual(probe.read_text(), str(probe.parent.resolve()))

    def test_successful_build_reclaims_invisible_buildah_work_containers(self):
        # A successful build can leave external Buildah "Storage" containers
        # that ordinary podman ps/prune cannot see. Cleanup must run before the
        # lease closes even when the monitored process group exited cleanly.
        proof = {"removed_external_build_containers": [["abcdef012345", "debian-working-container"]],
                 "dedicated_store_bytes_after_cleanup": 0}
        with patch(
            "assembler_bench.exploratory_runtime.launch.clean_stopped_build",
            return_value=proof,
        ) as cleaner:
            result = self.run_job()
        cleaner.assert_called_once()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["orphan_cleanup"], proof)
        self.assertNotIn("orphan_cleanup_error", result)
        self.assertNotIn("lease_state", result)

    def test_successful_build_without_cleanup_proof_keeps_lease_active(self):
        # Fail closed: an unrecognized or unmeasurable external container must
        # not release the worker lease or delete this job's forensic scratch.
        with patch(
            "assembler_bench.exploratory_runtime.launch.clean_stopped_build",
            side_effect=RuntimeError("unrecognized external container; stop cleanup"),
        ):
            result = self.run_job()
        self.assertEqual(result["status"], "finished")
        self.assertIn("unrecognized", result["orphan_cleanup_error"])
        self.assertEqual(result["lease_state"], "active_unreleased")
        self.assertEqual(result["job_temp_cleanup"]["removed"], False)

    def test_empty_cleanup_proof_never_releases_lease(self):
        # Absence of an error is not proof of teardown.
        with patch(
            "assembler_bench.exploratory_runtime.launch.clean_stopped_build",
            return_value={},
        ):
            result = self.run_job()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["lease_state"], "active_unreleased")

    def test_unbuilt_source_cannot_pilot(self):
        with self.assertRaises(ValueError):
            self.run_job("pilot")

    def test_changed_store_is_rejected(self):
        (self.root / "storage.conf").write_text("[storage]\ndriver = 'vfs'\n")
        with self.assertRaises(ValueError):
            self.run_job()

    def test_global_single_worker_lock(self):
        with (self.root / ".global-worker.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_job()

    def test_insufficient_free_space_blocks_before_spawn(self):
        with (
            patch("assembler_bench.exploratory_space.available", return_value=0),
            self.assertRaisesRegex(ValueError, "workspace reserve"),
        ):
            self.run_job()
        self.assertFalse(list(self.root.glob("run-*.json")))

    def test_tampered_baseline_rejected(self):
        self.baseline.write_text(self.baseline.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "changed disk baseline"):
            self.run_job()

    def test_measurement_failure_preserves_root_cause_but_never_passes(self):
        from assembler_bench.exploratory_runtime.monitor import GuardExceeded

        def failing_monitor(*args, **kwargs):
            try:
                raise OSError("rootless overlay accounting unavailable")
            except OSError as exc:
                raise GuardExceeded("measurement_unavailable") from exc

        with patch("assembler_bench.exploratory_runtime.launch.watch",
                   side_effect=failing_monitor):
            result = self.run_job(argv=[
                sys.executable, "-c", "import time;time.sleep(9)"])
        self.assertEqual(result["status"], "killed")
        self.assertEqual(result["reason"], "measurement_unavailable")
        self.assertEqual(result["measurement_error_type"], "OSError")
        self.assertIn("rootless overlay", result["measurement_error"])
        self.assertEqual(len(list(self.root.glob("run-*.json"))), 1)

    def test_guard_violation_kills_group_and_records(self):
        from assembler_bench.exploratory_runtime.monitor import GuardExceeded
        with patch("assembler_bench.exploratory_runtime.launch.watch",
                   side_effect=GuardExceeded("disk_limit")):
            result = self.run_job(argv=[sys.executable, "-c", "import time;time.sleep(9)"])
        self.assertEqual(result["status"], "killed")
        self.assertEqual(result["reason"], "disk_limit")
        self.assertEqual(len(list(self.root.glob("run-*.json"))), 1)
