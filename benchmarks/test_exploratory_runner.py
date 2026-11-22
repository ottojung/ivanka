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

        def failing_monitor(*args):
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
