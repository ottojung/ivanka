"""Smoke-test relocatable MiCall benchmark entrypoints without starting Podman."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent


class PortableLauncherTest(unittest.TestCase):
    def test_explicit_python_environment_runs_argument_parser(self):
        env = {**os.environ, "IVANKA_BENCH_PYTHON": sys.executable}
        for name in ("benchmark_podman_full_micall.sh",
                     "prepare_full_micall_iva_baselines.sh"):
            with self.subTest(script=name):
                result = subprocess.run(
                    [str(ROOT / "scripts" / name), "--help"],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                    timeout=20, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--cache-status", result.stdout)
                self.assertIn("--qualify-198", result.stdout)


if __name__ == "__main__":
    unittest.main()
