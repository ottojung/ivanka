"""CPU-only tests for short-locked, fail-closed Podman lifecycle."""
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import podman_detached_lifecycle as lifecycle


class DetachedLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock = Path(self.tmp.name) / "podman.lock"
        patcher = patch.object(lifecycle, "LIFECYCLE_LOCK", self.lock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.calls = []
        self.exit = {}
        self.command = [
            "podman", "run", "--rm", "--pull=never", "--name", "test-case",
            "--timeout", "1780", "--entrypoint", "python",
            "a" * 64, "/ivanka-timer.py",
        ]

    def fake(self, argv, *, stdout, stderr, timeout, check):
        self.calls.append(list(argv))
        stage = argv[1]
        if stage == "create":
            self.assertNotIn("--rm", argv)
            self.assertIn("a" * 64, argv)
        code = self.exit.get(stage, 0)
        if stage == "logs" and not code:
            stdout.write("micall.process_run(): Done.\n")
        data = ("b" * 64 if stage == "create" and code == 0 else
                "0\n" if stage == "wait" else "")
        return subprocess.CompletedProcess(argv, code, data.encode())

    def run_case(self, remaining=1800):
        with patch.object(lifecycle.subprocess, "run", side_effect=self.fake):
            return lifecycle.run_detached(
                self.command, self.stdout, self.stderr, remaining)

    def test_success_requires_all_five_steps(self):
        result = self.run_case()
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "wait", "logs", "rm"])
        self.assertIn("Done.", self.stdout.getvalue())

    def test_create_failure_does_not_start_or_remove(self):
        self.exit["create"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 125)
        self.assertEqual([c[1] for c in self.calls], ["create"])

    def test_partial_create_response_is_not_retried(self):
        self.exit["create"] = 125
        def partial(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "create":
                return subprocess.CompletedProcess(argv, 125, b"b" * 64)
            return result
        with patch.object(lifecycle.subprocess, "run", side_effect=partial):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls], ["create"])

    def test_start_failure_is_not_retriable_create_failure(self):
        self.exit["start"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "rm"])
        self.assertIn("start failure", self.stderr.getvalue())

    def test_wait_failure_fails_closed_and_forces_cleanup(self):
        self.exit["wait"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "wait", "wait", "wait", "wait", "rm"])

    def test_logs_failure_fails_closed(self):
        self.exit["logs"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "wait", "logs", "rm"])

    def test_removal_failure_never_qualifies(self):
        self.exit["rm"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "wait", "logs", "rm", "rm", "rm", "rm", "rm"])

    def test_transient_wait_and_removal_failures_retry_without_reexecution(self):
        counts = {"wait": 0, "rm": 0}
        def flaky(argv, **kwargs):
            stage = argv[1]
            if stage in counts:
                counts[stage] += 1
                if counts[stage] == 1:
                    return subprocess.CompletedProcess(argv, 125, b"")
            return self.fake(argv, **kwargs)
        with patch.object(lifecycle.subprocess, "run", side_effect=flaky):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(counts, {"wait": 2, "rm": 2})
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_transient_logs_failure_discards_partial_output(self):
        seen = 0

        def flaky(argv, **kwargs):
            nonlocal seen
            if argv[1] == "logs":
                seen += 1
                if seen == 1:
                    self.calls.append(list(argv))
                    kwargs["stdout"].write("partial failed log\\n")
                    return subprocess.CompletedProcess(argv, 125, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle.subprocess, "run", side_effect=flaky):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(seen, 2)
        self.assertEqual(self.stdout.getvalue(), "micall.process_run(): Done.\\n")
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_persistent_logs_failure_rejects_without_reexecution(self):
        self.exit["logs"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sum(c[1] == "logs" for c in self.calls), 4)
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_deadline_does_not_launch(self):
        result = self.run_case(remaining=0)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(self.calls, [])

    def test_nonzero_micall_exit_is_preserved(self):
        def fake(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, b"42\n")
            return result
        with patch.object(lifecycle.subprocess, "run", side_effect=fake):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(self.calls[-1][1], "rm")


if __name__ == "__main__":
    unittest.main()
