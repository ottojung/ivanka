"""Compressed-table readers must import under the project-path Pages entrypoint."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CompressedTableImportContextTests(unittest.TestCase):
    def test_pages_entrypoint_builds_without_benchmarks_on_sys_path(self):
        # pages.yml runs `python -m benchmarks.assembler_bench.site_build` with no
        # PYTHONPATH=benchmarks. That import chain reaches project_references, so a
        # bare `from compressed_tables import ...` there fails in Pages even though
        # unittest discovery (which adds benchmarks/ to sys.path) stays green.
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            process = subprocess.run(
                [sys.executable, "-m", "benchmarks.assembler_bench.site_build",
                 "--output", str(output)],
                cwd=ROOT, env=environment, text=True, capture_output=True,
                timeout=120, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("PAGES_BUILD_VERIFIED", process.stdout)
            self.assertTrue((output / ".nojekyll").is_file())
            self.assertTrue((output / "bench" / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
