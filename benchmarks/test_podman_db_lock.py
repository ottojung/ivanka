"""Podman recovery: simulated command runner, no containers or private data."""
import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from container_completion import TIMING_ORIGIN

spec = importlib.util.spec_from_file_location(
    "podman_compare_lock_test", Path(__file__).with_name("podman_full_micall.py"))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

POSTRUN_ID = "a" * 64
POSTRUN_ERROR = (
    'time="2026-11-01T08:57:24Z" level=error msg="Removing container '
    f'{POSTRUN_ID}: retrieving container {POSTRUN_ID} '
    f'configuration from DB to remove: retrieving container {POSTRUN_ID} '
    'config from DB: database is locked"\n'
)

PRESTART_SAVE = (
    f"Error: saving container {POSTRUN_ID} state: beginning container "
    f"{POSTRUN_ID} save transaction: database is locked\n"
)
POSTRUN_SAVE = (
    'time="2026-11-01T09:07:23Z" level=error msg="Removing container '
    f'{POSTRUN_ID}: cleaning up container {POSTRUN_ID}: '
    f'unmounting container {POSTRUN_ID} storage: unmounting container '
    f'{POSTRUN_ID}: saving container {POSTRUN_ID} state: beginning container '
    f'{POSTRUN_ID} save transaction: database is locked"\n'
)


class PodmanLockTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "samples" / "TEST"
        source.mkdir(parents=True)
        for mate in (1, 2):
            (source / f"TEST_L001_R{mate}_001.fastq.gz").write_bytes(b"placeholder")
        self.folder = self.root / "results" / "invocation" / "TEST" / "ivanka"

    def simulate(self, responses):
        calls = []
        def run(command, *, stdout, stderr, timeout, check):
            calls.append(command[:])
            response = responses[len(calls) - 1]
            returncode, stderr_text, timing = response[:3]
            stderr.write(stderr_text)
            if len(response) > 3:
                stdout.write(response[3])
            if len(response) > 4 and response[4]:
                (self.folder / "conseq.csv").write_text("partial MiCall artifact")
            if timing:
                (self.folder / "micall_internal_timing.json").write_text(
                    json.dumps({"exit_code": 0, "seconds": 0.02,
                                "timing_origin": TIMING_ORIGIN}))
            return CompletedProcess(command, returncode)
        with patch.object(benchmark, "DATA", self.root), \
             patch.object(benchmark, "RESULTS", self.root / "results"), \
             patch.object(benchmark, "score_outputs", return_value={"outputs": {}}), \
             patch.object(benchmark.subprocess, "run", side_effect=run), \
             patch.object(benchmark.time, "sleep", return_value=None):
            result = benchmark.run_arm(
                {"sample": "TEST"}, "ivanka", "b" * 64,
                None, 14, "invocation", all_projects=True)
        return result, calls

    def test_startup_database_lock_retries_and_never_forges_micall_runtime(self):
        result, calls = self.simulate([
            (125, "Error: beginning container create transaction: database is locked\n", False),
            (0, "2026-11-01[INFO]micall.process_run(): Done.\n", True),
        ])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["seconds"], 0.02)
        self.assertEqual(result["podman_start_retries"], 1)
        name_index = calls[0].index("--name") + 1
        self.assertNotEqual(calls[0][name_index], calls[1][name_index])
        self.assertTrue(calls[1][name_index].endswith("-dbretry1"))
        self.assertLessEqual(float(calls[1][calls[1].index("--timeout") + 1]), 14)

    def test_exact_prestart_save_state_exit126_retries_with_same_deadline(self):
        result, calls = self.simulate([
            (126, PRESTART_SAVE, False),
            (0, "2026-11-01[INFO]micall.process_run(): Done.\n", True),
        ])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["podman_start_retries"], 1)
        self.assertEqual(result["seconds"], 0.02)
        self.assertLessEqual(float(calls[1][calls[1].index("--timeout") + 1]), 14)

    def test_mixed_prestart_lock_retries_keep_one_deadline(self):
        result, calls = self.simulate([
            (125, "Error: beginning transaction: database is locked\n", False),
            (126, PRESTART_SAVE, False),
            (0, "2026-11-01[INFO]micall.process_run(): Done.\n", True),
        ])
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["podman_start_retries"], 2)
        self.assertEqual(result["seconds"], 0.02)
        self.assertLessEqual(float(calls[2][calls[2].index("--timeout") + 1]), 14)

    def test_prestart_lock_with_micall_stdout_is_not_safe_to_retry(self):
        result, calls = self.simulate([
            (125, "Error: beginning transaction: database is locked\\n",
             False, "MiCall may have started"),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 125)
        self.assertNotIn("podman_start_retries", result)

    def test_prestart_save_lock_with_partial_artifact_is_not_retried(self):
        result, calls = self.simulate([
            (126, PRESTART_SAVE, False, "", True),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 126)
        self.assertNotIn("podman_start_retries", result)

    def test_generic_startup_error_never_retries(self):
        result, calls = self.simulate([
            (125, "Error: missing executable\n", False),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 125)
        self.assertNotIn("seconds", result)

    def test_postrun_cleanup_failure_records_raw_exit_and_valid_timer(self):
        result, calls = self.simulate([
            (127, "2026-11-01[INFO]micall.process_run(): Done.\n"
                  + POSTRUN_ERROR, True),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["podman_exit_code"], 127)
        self.assertEqual(result["seconds"], 0.02)
        self.assertEqual(result["timing_origin"], TIMING_ORIGIN)

    def test_save_state_cleanup_exit127_recovers_only_authenticated_micall(self):
        result, calls = self.simulate([
            (127, "2026-11-01[INFO]micall.process_run(): Done.\n"
                  + POSTRUN_SAVE, True),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["podman_exit_code"], 127)
        self.assertEqual(result["seconds"], 0.02)

    def test_postrun_failure_without_completion_remains_failure(self):
        result, calls = self.simulate([
            (127, POSTRUN_ERROR, True),
        ])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["exit_code"], 127)
        self.assertNotIn("seconds", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
