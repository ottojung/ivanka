"""Tests for fail-closed in-container MiCall runtime evidence."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

module_path = Path(__file__).with_name("inside_container_timing.py")
spec = importlib.util.spec_from_file_location("ivanka_container_timer", module_path)
timer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timer)


class ContainerTimingTests(TestCase):
    def test_success_persists_atomic_monotonic_measurement(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "elapsed.json"
            with patch.object(timer.sys, "argv",
                              ["timer.py", str(output), "micall", "analyze"]), \
                 patch.object(timer.subprocess, "call", return_value=0) as run:
                self.assertEqual(timer.main(), 0)
            run.assert_called_once_with(["micall", "analyze"])
            recorded = json.loads(output.read_text())
            self.assertEqual(recorded["timing_origin"], timer.TIMING_ORIGIN)
            self.assertEqual(recorded["exit_code"], 0)
            self.assertGreaterEqual(recorded["seconds"], 0)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_failed_child_cannot_be_confused_with_success(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "elapsed.json"
            with patch.object(timer.sys, "argv",
                              ["timer.py", str(output), "micall"]), \
                 patch.object(timer.subprocess, "call", return_value=2):
                self.assertEqual(timer.main(), 2)
            recorded = json.loads(output.read_text())
            self.assertEqual(recorded["exit_code"], 2)

    def test_old_control_rejected_for_strict_timing(self):
        from unittest.mock import patch
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "benchmark", Path(__file__).with_name("podman_full_micall.py"))
        benchmark = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(benchmark)
        with patch.object(benchmark, "baseline_provenance", return_value={}), \
             patch.object(benchmark, "load_iva_baseline",
                          return_value={"exit_code": 0, "seconds": 9.3}):
            rows = [{"sample": "S1"}]
            old = benchmark.iva_cache_status(rows, "iva", "ref", True)
            strict = benchmark.iva_cache_status(
                rows, "iva", "ref", True, require_internal_timing=True)
            self.assertEqual(old["verified"], ["S1"])
            self.assertEqual(strict["missing_or_invalid"], ["S1"])
