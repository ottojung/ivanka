"""The frozen run's container settings must be explicit and reviewable."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ReadBackedBuildRecipeTests(unittest.TestCase):
    def test_current_container_has_explicit_qualified_configuration(self):
        recipe = (ROOT / "benchmarks/Dockerfile.read-backed").read_text()
        for setting in (
            "IVANKA_BENCH_PRIMARY_SEEDS=${NATIVE_PRIMARY_SEEDS}",
            "IVANKA_BENCH_RESCUE_SEEDS=${NATIVE_RESCUE_SEEDS}",
            "ARG NATIVE_PRIMARY_SEEDS=50",
            "ARG NATIVE_RESCUE_SEEDS=20",
            "ARG POSTSELECT_CONTIGS=1",
            "IVANKA_READ_BACKED_TILE_SPAN=2000",
            "IVANKA_READ_BACKED_TILE_OVERLAP=512",
            "IVANKA_TRIM_SUPPORTED_ISLAND=1",
            'org.ottojung.ivanka.source-commit="${SOURCE_COMMIT}"',
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, recipe)

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
