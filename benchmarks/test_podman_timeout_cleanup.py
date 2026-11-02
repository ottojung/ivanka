"""Timeout provenance must survive a stalled Podman cleanup.

These tests mock Podman and never start a container.
"""
import importlib.util
from contextlib import nullcontext
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
    def run_timeout(self, cleanup, clock=None, expected_calls=2, cleanup_timeout=None):
        clock_context = (patch.object(benchmark.time, "monotonic", side_effect=clock)
                         if clock is not None else nullcontext())
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
                              side_effect=[TimeoutExpired(["podman", "run"], 15), cleanup]) as run, \
                 clock_context:
                result = benchmark.run_arm(
                    {"sample": "TEST"}, "iva", "a" * 64,
                    None, 15, "invocation", all_projects=True)
            self.assertEqual(run.call_count, expected_calls)
            if expected_calls == 2:
                self.assertEqual(run.call_args.args[0][:3], ["podman", "rm", "--force"])
                if cleanup_timeout is not None:
                    self.assertEqual(run.call_args.kwargs["timeout"], cleanup_timeout)
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


    def test_cleanup_consumes_only_remaining_original_budget(self):
        self.run_timeout(Mock(returncode=0), clock=[100, 100, 114, 114],
                         cleanup_timeout=1)

    def test_cleanup_not_launched_after_deadline(self):
        result = self.run_timeout(Mock(returncode=0),
                                  clock=[100, 100, 115, 115], expected_calls=1)
        self.assertIn("deadline exhausted", result["cleanup_error"])
