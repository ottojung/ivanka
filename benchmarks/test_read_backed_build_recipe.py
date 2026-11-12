"""The frozen run's container settings must be explicit and reviewable."""
from pathlib import Path
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

    def test_qualified_selection_defaults_are_in_code(self):
        rust = (ROOT / "src/assembler/run_seed/assembly/experiment_budget.rs").read_text()
        selector = (ROOT / "benchmarks/ivanka_read_support_selector.py").read_text()
        self.assertIn('validate(primary.as_deref(), 50,', rust)
        self.assertIn('validate(rescue.as_deref(), 20,', rust)
        for setting in (
            'os.environ.get("IVANKA_POSTSELECT_CONTIGS", "1")',
            'os.environ.get("IVANKA_SUPPORT_PAIRS", "80000")',
            'os.environ.get("IVANKA_TRIM_UNSUPPORTED_TERMINI", "1")',
            'os.environ.get("IVANKA_TRIM_SUPPORTED_ISLAND", "1")',
            'os.environ.get("IVANKA_READ_BACKED_TILE_SPAN", "2000")',
            'os.environ.get("IVANKA_READ_BACKED_TILE_OVERLAP", "512")',
        ):
            self.assertIn(setting, selector)

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
        proc = subprocess.run(
            ["sh", str(script), "localhost/micall:ivanka-read-backed-bad"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Image tag must start", proc.stderr)
