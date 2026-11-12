"""The frozen run's container settings must be explicit and reviewable."""
from pathlib import Path
import os
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ReadBackedBuildRecipeTests(unittest.TestCase):
    def test_default_execution_requires_no_benchmark_environment(self):
        recipe = (ROOT / "benchmarks/Dockerfile.read-backed").read_text()
        self.assertNotIn("ENV IVANKA_", recipe)
        self.assertNotIn("ARG NATIVE_PRIMARY_SEEDS", recipe)
        self.assertNotIn("ARG NATIVE_RESCUE_SEEDS", recipe)
        self.assertNotIn("ARG POSTSELECT_CONTIGS", recipe)
        self.assertIn(
            'org.ottojung.ivanka.source-commit="${SOURCE_COMMIT}"', recipe,
        )

    def test_rust_default_executes_read_backed_selection(self):
        budget = (ROOT / "src/assembler/run_seed/assembly/experiment_budget.rs").read_text()
        finish = (ROOT / "src/assembler/run/write_results.rs").read_text()
        selector = (ROOT / "src/assembler/run/read_backed/mod.rs").read_text()
        recipe = (ROOT / "benchmarks/Dockerfile.read-backed").read_text()
        self.assertIn("let limits = (50, 20);", budget)
        self.assertNotIn("std::env", budget)
        self.assertIn("read_backed::write(out, contigs, reads)", finish)
        self.assertIn("tiling::partition", selector)
        self.assertIn("/usr/local/bin/ivanka", recipe)
        self.assertNotIn("/usr/local/bin/ivanka-native", recipe)
        self.assertNotIn("COPY benchmarks/ivanka_read_support_selector.py", recipe)

    def test_build_script_pins_base_and_source(self):
        script = ROOT / "scripts/build_read_backed_image.sh"
        body = script.read_text()
        self.assertIn("a5d4923e28f3d7b9725a375d51e34", body)
        self.assertIn("git status --porcelain", body)
        self.assertIn("ivanka-milestone198-exclusive.lock", body)
        self.assertIn("--pull=never", body)
        self.assertIn('--build-arg SOURCE_COMMIT="$source_commit"', body)
        subprocess.run(["sh", "-n", str(script)], check=True)

    def test_wrong_source_tag_is_rejected_before_any_build(self):
        script = ROOT / "scripts/build_read_backed_image.sh"
        with tempfile.TemporaryDirectory() as folder:
            # The test must not depend on a Git worktree mounted into a
            # container at the original absolute host path.
            fake_git = Path(folder) / "git"
            fake_git.write_text("#!/bin/sh\necho 123456789abc123456789abc123456789abc12345678\n")
            fake_git.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = folder + os.pathsep + environment.get("PATH", "")
            proc = subprocess.run(
                ["sh", str(script), "localhost/micall:ivanka-read-backed-bad"],
                env=environment, text=True, capture_output=True, check=False,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Image tag must start", proc.stderr)
