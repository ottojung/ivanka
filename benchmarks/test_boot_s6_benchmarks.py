"""Host-independent tests for idempotent s6 benchmark restart."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("boot_s6_benchmarks.sh")


class S6BootTests(unittest.TestCase):
    def run_script(self, root, control):
        env = os.environ.copy()
        env.update({"IVANKA_BENCH_SERVICE_ROOT": str(root),
                    "IVANKA_BENCH_S6_CONTROL": str(control),
                    "IVANKA_BENCH_S6_SCAN": "/bin/true"})
        return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True,
                              text=True, timeout=10)

    def test_missing_benchmark_root_is_optional(self):
        with tempfile.TemporaryDirectory() as name:
            self.assertEqual(self.run_script(Path(name)/"missing", "/bin/false").returncode, 0)

    def test_rejects_incomplete_service_tree(self):
        with tempfile.TemporaryDirectory() as name:
            outcome = self.run_script(Path(name), "/bin/false")
            self.assertEqual(outcome.returncode, 1)
            self.assertIn("incomplete", outcome.stderr)

    def test_existing_healthy_supervisor_starts_no_new_scanner(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for child in ("publisher", "bridge-original-pair-v2-all400"):
                (root/child).mkdir()
                run=root/child/"run"
                run.write_text("#!/bin/sh\nexit 0\n")
                run.chmod(0o755)
            control=root/"live-control.sh"
            control.write_text("#!/bin/sh\nexit 0\n")
            control.chmod(0o755)
            result=self.run_script(root, control)
            self.assertEqual(result.returncode, 0)
            self.assertFalse((root/"supervisor.log").exists())


if __name__ == "__main__":
    unittest.main()
