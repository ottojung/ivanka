"""Single-worker real process-group supervision and immutable storage checks."""
import copy
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
        base = {"root": str(self.root), "image_store": str(self.store),
                "workspace": str(self.root)}
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps(base))
        self.policy["storage_baseline_sha256"] = hashlib.sha256(
            self.baseline.read_bytes()).hexdigest()
        self.config = patch("assembler_bench.exploratory_runtime.setup.checked",
                            return_value=self.policy)
        self.admission = patch("assembler_bench.exploratory_runtime.launch.admit",
                               return_value={})
        self.config.start()
        self.admission.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.admission.stop)

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

    def test_guard_violation_kills_group_and_records(self):
        from assembler_bench.exploratory_runtime.monitor import GuardExceeded
        with patch("assembler_bench.exploratory_runtime.launch.watch",
                   side_effect=GuardExceeded("disk_limit")):
            result = self.run_job(argv=[sys.executable, "-c", "import time;time.sleep(9)"])
        self.assertEqual(result["status"], "killed")
        self.assertEqual(result["reason"], "disk_limit")
        self.assertEqual(len(list(self.root.glob("run-*.json"))), 1)
