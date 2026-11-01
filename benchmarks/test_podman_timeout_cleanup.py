"""Timeout provenance must survive a stalled Podman cleanup.

These tests mock Podman and never start a container.
"""
import importlib.util
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    "podman_compare", Path(__file__).with_name("podman_full_micall.py"))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class PodmanCleanupTests(TestCase):
    def run_timeout(self, cleanup):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reads = root / "samples" / "TEST"
            reads.mkdir(parents=True)
            for mate in (1, 2):
                (reads / f"TEST_L001_R{mate}_001.fastq.gz").write_bytes(b"placeholder")
            with patch.object(benchmark, "DATA", root), \
                 patch.object(benchmark, "RESULTS", root / "results"), \
                 patch.object(benchmark, "score_outputs", return_value={"outputs": {}}), \
                 patch.object(benchmark.subprocess, "run",
                              side_effect=[TimeoutExpired(["podman", "run"], 15), cleanup]) as run:
                result = benchmark.run_arm(
                    {"sample": "TEST"}, "iva", "a" * 64,
                    None, 15, "invocation", all_projects=True)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][:3], ["podman", "rm", "--force"])
            self.assertEqual(result["exit_code"], 124)
            self.assertIn("timed out", result["error"])
            self.assertNotIn("seconds", result)
            return result

    def test_cleanup_timeout_preserves_original_failure(self):
        result = self.run_timeout(TimeoutExpired(["podman", "rm"], 30))
        self.assertIn("TimeoutExpired", result["cleanup_error"])

    def test_cleanup_nonzero_preserves_original_failure(self):
        result = self.run_timeout(Mock(returncode=9))
        self.assertIn("exited 9", result["cleanup_error"])

    def test_successful_micall_with_failed_cleanup_fails_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reads = root / "samples" / "TEST"
            reads.mkdir(parents=True)
            for mate in (1, 2):
                (reads / f"TEST_L001_R{mate}_001.fastq.gz").write_bytes(b"placeholder")

            def execute(command, **kwargs):
                if command[:2] == ["podman", "run"]:
                    timer = root / "results" / "invocation" / "TEST" / "ivanka" / "micall_internal_timing.json"
                    timer.write_text('{"timing_origin":"micall_in_container_monotonic_v1","seconds":1.0,"exit_code":0}')
                    return Mock(returncode=0)
                return Mock(returncode=9)

            with patch.object(benchmark, "DATA", root), \
                 patch.object(benchmark, "RESULTS", root / "results"), \
                 patch.object(benchmark, "score_outputs", return_value={"outputs": {}}), \
                 patch.object(benchmark.subprocess, "run", side_effect=execute) as runner:
                result = benchmark.run_arm(
                    {"sample": "TEST"}, "ivanka", "a" * 64,
                    None, 15, "invocation", all_projects=True)
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(result["exit_code"], 1)
            self.assertIn("teardown incomplete", result["error"])
            self.assertIn("exited 9", result["cleanup_error"])
            self.assertNotIn("seconds", result)
