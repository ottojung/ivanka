"""CPU-only tests for short-locked, fail-closed Podman lifecycle."""
import io
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import podman_detached_lifecycle as lifecycle


class OwnedPodmanSubprocessTests(unittest.TestCase):
    def test_successful_group_is_captured(self):
        with patch.object(lifecycle.subprocess, "Popen") as popen:
            instance = popen.return_value
            instance.returncode = 0
            instance.communicate.return_value = (b"result", None)
            result = lifecycle._run_command(
                ["podman", "create"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=20)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"result")

    def test_timeout_kills_only_owned_session_group(self):
        import signal
        with patch.object(lifecycle.subprocess, "Popen") as popen, \
             patch.object(lifecycle.os, "killpg") as terminate:
            instance = popen.return_value
            instance.pid = 987654
            instance.communicate.side_effect = [
                subprocess.TimeoutExpired(["podman", "create"], 2),
                (b"", None)]
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                lifecycle._run_command(
                    ["podman", "create", "-c", "PRIVATE-VERIFIER-SOURCE"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=2)
        self.assertEqual(caught.exception.cmd, ["podman", "create"])
        self.assertNotIn("PRIVATE-VERIFIER-SOURCE", str(caught.exception))
        terminate.assert_called_once_with(987654, signal.SIGKILL)
        self.assertEqual(instance.communicate.call_count, 2)


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
            self.assertNotIn("--rm", argv[:argv.index("a" * 64)])
            self.assertIn("a" * 64, argv)
        code = self.exit.get(stage, 0)
        if stage == "logs" and not code:
            stdout.write("micall.process_run(): Done.\n")
        data = ("b" * 64 if stage == "create" and code == 0 else
                "0\n" if stage == "wait" else "")
        return subprocess.CompletedProcess(argv, code, data.encode())

    def run_case(self, remaining=1800):
        with patch.object(lifecycle, "_run_command", side_effect=self.fake):
            return lifecycle.run_detached(
                self.command, self.stdout, self.stderr, remaining)

    def test_eight_concurrent_runs_serialize_only_metadata(self):
        # Simulates SQLite failing whenever two create/start/rm transactions
        # overlap, while proving independent container execution overlaps.
        counters = {"metadata": 0, "max_metadata": 0,
                    "wait": 0, "max_wait": 0}
        guard = threading.Lock()
        wait_barrier = threading.Barrier(8)

        def fake(argv, *, stdout, stderr, timeout, check):
            stage = argv[1]
            name = "metadata" if stage in ("create", "start", "rm") else (
                "wait" if stage == "wait" else None)
            if name:
                with guard:
                    counters[name] += 1
                    counters["max_" + name] = max(
                        counters["max_" + name], counters[name])
            try:
                if name == "wait":
                    # Eight different MiCall executions must be able to
                    # reach wait simultaneously without holding the DB lock.
                    wait_barrier.wait(timeout=8)
                time.sleep(0.008 if name == "metadata" else
                           0.035 if name == "wait" else 0.001)
            finally:
                if name:
                    with guard:
                        counters[name] -= 1
            if stage == "create":
                requested = argv[argv.index("--name") + 1]
                data = hashlib.sha256(requested.encode()).hexdigest().encode()
            elif stage == "wait":
                data = b"0\n"
            else:
                data = b""
            if stage == "logs":
                stdout.write("micall.process_run(): Done.\n")
            return subprocess.CompletedProcess(argv, 0, data)

        def one(index):
            cmd = list(self.command)
            cmd[cmd.index("--name") + 1] = f"test-case-{index}"
            return lifecycle.run_detached(cmd, io.StringIO(), io.StringIO(), 10)

        with patch.object(lifecycle, "_run_command", side_effect=fake):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(one, range(8)))
        self.assertTrue(all(r.returncode == 0 and r.stage == "complete"
                            for r in results))
        self.assertEqual(counters["max_metadata"], 1)
        self.assertGreater(counters["max_wait"], 1)

    def test_real_subprocess_lifecycle_with_file_backed_logs(self):
        # Exercise real Popen/communicate and owned sessions, not mocks.
        # A temporary executable simulates Podman's CLI without containers.
        import os
        command = Path(self.tmp.name) / "podman"
        command.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  create) printf '%064d\\n' 0;;\n"
            "  start) exit 0;;\n"
            "  wait) printf '0\\n';;\n"
            "  logs) printf 'micall.process_run(): Done.\\n';;\n"
            "  rm) exit 0;;\n"
            "  *) exit 125;;\n"
            "esac\n")
        command.chmod(0o755)
        with patch.dict(os.environ, {"PATH": self.tmp.name + os.pathsep +
                                      os.environ.get("PATH", "")}):
            with tempfile.TemporaryFile(mode="w+t") as output, \
                 tempfile.TemporaryFile(mode="w+t") as errors:
                result = lifecycle.run_detached(self.command, output,
                                                errors, remaining=10)
                output.seek(0)
                errors.seek(0)
                self.assertEqual((result.returncode, result.stage),
                                 (0, "complete"), errors.read())
                self.assertIn("micall.process_run(): Done.", output.read())

    def test_success_requires_all_five_steps(self):
        result = self.run_case()
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual([c[1] for c in self.calls],
                         ["create", "start", "wait", "logs", "rm"])
        self.assertIn("Done.", self.stdout.getvalue())

    def test_image_argv_named_rm_is_not_stripped(self):
        # Only the Podman auto-removal flag may be removed. An identically
        # named MiCall argument is data and must survive the transformation.
        self.command.extend(["--rm", "--project_code", "sample"])
        result = self.run_case()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls[0][1], "create")
        self.assertEqual(self.calls[0][-3:], ["--rm", "--project_code", "sample"])
        self.assertEqual(self.calls[0].count("--rm"), 1)

    def test_invalid_wait_accepts_only_authenticated_exited_same_id(self):
        commands = []
        state = {
            "Status": "exited", "Running": False, "OOMKilled": False,
            "Dead": False, "ExitCode": 0,
            "StartedAt": "2026-11-13T12:00:00Z",
            "FinishedAt": "0001-01-01T00:00:00Z",
        }

        def corrupted(argv, **kwargs):
            commands.append(list(argv))
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, b"invalid status")
            if argv[1] == "inspect":
                return subprocess.CompletedProcess(
                    argv, 0, json.dumps(state).encode())
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=corrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual(sum(row[1] == "start" for row in commands), 1)
        self.assertEqual(sum(row[1] == "wait" for row in commands), 3)
        inspections = [row for row in commands if row[1] == "inspect"]
        self.assertEqual(len(inspections), 1)
        self.assertEqual(inspections[0][-1], "b" * 64)
        self.assertIn("verified terminal exit", self.stderr.getvalue())
        self.assertIn("Done.", self.stdout.getvalue())

    def test_invalid_wait_never_authenticates_incomplete_or_dead_container(self):
        cases = [
            {"Status": "running", "Running": True},
            {"Status": "created", "Running": False},
            {"Status": "exited", "Running": False, "OOMKilled": True},
            {"Status": "exited", "Running": False, "Dead": True},
            {"Status": "exited", "Running": False, "ExitCode": "0"},
            {"Status": "exited", "Running": False,
             "StartedAt": "0001-01-01T00:00:00Z"},
        ]
        base = {"Status": "exited", "Running": False, "OOMKilled": False,
                "Dead": False, "ExitCode": 0,
                "StartedAt": "2026-11-13T12:00:00Z"}

        for altered in cases:
            with self.subTest(altered=altered):
                observed = []
                state = {**base, **altered}

                def corrupted(argv, **kwargs):
                    observed.append(list(argv))
                    if argv[1] == "wait":
                        return subprocess.CompletedProcess(argv, 0, b"bad")
                    if argv[1] == "inspect":
                        return subprocess.CompletedProcess(
                            argv, 0, json.dumps(state).encode())
                    return self.fake(argv, **kwargs)

                with patch.object(lifecycle, "_run_command",
                                  side_effect=corrupted):
                    outcome = lifecycle.run_detached(
                        self.command, io.StringIO(), io.StringIO(), 1800)
                self.assertEqual((outcome.returncode, outcome.stage),
                                 (1, "wait"))
                self.assertNotIn("logs", [row[1] for row in observed])
                self.assertEqual(sum(row[1] == "start" for row in observed), 1)

    def test_inspect_unreadable_state_remains_unqualified(self):
        def unreadable(argv, **kwargs):
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, b"garbage")
            if argv[1] == "inspect":
                return subprocess.CompletedProcess(argv, 0, b"{not-json")
            return self.fake(argv, **kwargs)
        with patch.object(lifecycle, "_run_command", side_effect=unreadable):
            outcome = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((outcome.returncode, outcome.stage), (1, "wait"))

    def test_missing_pinned_auto_remove_flag_is_rejected(self):
        self.command.remove("--rm")
        with self.assertRaisesRegex(ValueError, "pinned podman run"):
            self.run_case()
        self.assertEqual(self.calls, [])

    def test_create_failure_does_not_start_or_remove(self):
        self.exit["create"] = 125
        result = self.run_case()
        self.assertEqual(result.returncode, 125)
        self.assertEqual([c[1] for c in self.calls], ["create"])

    def test_failed_create_without_id_reclaims_owned_name(self):
        # SQLite lock failures can occur after Podman commits a name but
        # before it emits an immutable ID. Never retry or start MiCall.
        name = "ivanka-bench-ivanka-1793586776-32030-69942039"
        self.command[self.command.index("--name") + 1] = name
        self.exit["create"] = 125
        result = self.run_case()
        self.assertEqual((result.returncode, result.stage), (125, "create"))
        self.assertEqual([c[1] for c in self.calls], ["create", "rm"])
        self.assertEqual(self.calls[-1], ["podman", "rm", "--force", name])

    def test_failed_create_malformed_response_never_removes_by_name(self):
        name = "ivanka-bench-ivanka-1793586776-32030-69942039"
        self.command[self.command.index("--name") + 1] = name
        self.exit["create"] = 125

        def malformed(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "create":
                return subprocess.CompletedProcess(argv, 125, b"not-an-id")
            return result

        with patch.object(lifecycle, "_run_command", side_effect=malformed):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (1, "create"))
        self.assertEqual([c[1] for c in self.calls], ["create"])

    def test_partial_create_response_is_not_retried(self):
        self.exit["create"] = 125
        def partial(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "create":
                return subprocess.CompletedProcess(argv, 125, b"b" * 64)
            return result
        with patch.object(lifecycle, "_run_command", side_effect=partial):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[1] for c in self.calls], ["create", "rm"])
        self.assertNotIn("start", [c[1] for c in self.calls])

    def test_failed_create_with_unparseable_output_never_removes(self):
        self.exit["create"] = 125
        def malformed(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "create":
                return subprocess.CompletedProcess(argv, 125, b"not-a-container-id")
            return result
        with patch.object(lifecycle, "_run_command", side_effect=malformed):
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
                         ["create", "start", "wait", "logs", "logs",
                          "logs", "logs", "rm"])

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
        with patch.object(lifecycle, "_run_command", side_effect=flaky):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(counts, {"wait": 2, "rm": 2})
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_remove_timeout_retries_same_id_without_rerunning_micall(self):
        # S97: MiCall completed and logs were authenticated; only rm timed out.
        removals = []

        def flaky(argv, **kwargs):
            if argv[1] == "rm":
                removals.append(list(argv))
                if len(removals) == 1:
                    self.calls.append(list(argv))
                    raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if argv[1] == "container":
                return subprocess.CompletedProcess(argv, 0, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=flaky):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual(len(removals), 2)
        self.assertEqual(removals[0], removals[1])
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)
        self.assertEqual(sum(c[1] == "wait" for c in self.calls), 1)
        self.assertEqual(sum(c[1] == "logs" for c in self.calls), 1)
        self.assertIn("Done.", self.stdout.getvalue())

    def test_remove_timeout_then_verified_absence_qualifies(self):
        # Podman may finish deleting the ID before its rm CLI times out.
        observed = []

        def interrupted(argv, **kwargs):
            observed.append(list(argv))
            if argv[1] == "rm":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if argv[1] == "container":
                return subprocess.CompletedProcess(argv, 1, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=interrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual(sum(c[1] == "rm" for c in observed), 1)
        self.assertEqual(sum(c[1] == "container" for c in observed), 1)
        self.assertEqual(sum(c[1] == "start" for c in observed), 1)
        self.assertIn("Done.", self.stdout.getvalue())

    def test_remove_timeout_then_missing_on_retry_requires_absence(self):
        seen = 0
        observed = []

        def interrupted(argv, **kwargs):
            nonlocal seen
            observed.append(list(argv))
            if argv[1] == "rm":
                seen += 1
                if seen == 1:
                    raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
                return subprocess.CompletedProcess(argv, 125, b"")
            if argv[1] == "container":
                return subprocess.CompletedProcess(
                    argv, 0 if seen == 1 else 1, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=interrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        self.assertEqual(sum(c[1] == "rm" for c in observed), 2)
        self.assertEqual(sum(c[1] == "container" for c in observed), 2)
        self.assertEqual(sum(c[1] == "start" for c in observed), 1)

    def test_remove_timeout_unverifiable_absence_fails_closed(self):
        observed = []

        def interrupted(argv, **kwargs):
            observed.append(list(argv))
            if argv[1] == "rm":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if argv[1] == "container":
                return subprocess.CompletedProcess(argv, 125, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=interrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (124, "remove"))
        self.assertEqual(sum(c[1] == "start" for c in observed), 1)
        self.assertEqual(sum(c[1] == "rm" for c in observed), 5)
        self.assertEqual(sum(c[1] == "container" for c in observed), 4)

    def test_plain_remove_failure_cannot_be_laundered_by_absence(self):
        self.exit["rm"] = 125
        result = self.run_case()
        self.assertEqual((result.returncode, result.stage), (1, "remove"))
        self.assertNotIn("container", [c[1] for c in self.calls])

    def test_persistent_remove_timeouts_fail_closed(self):
        def stuck(argv, **kwargs):
            if argv[1] == "rm":
                self.calls.append(list(argv))
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if argv[1] == "container":
                return subprocess.CompletedProcess(argv, 0, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=stuck):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (124, "remove"))
        self.assertEqual(sum(c[1] == "rm" for c in self.calls), 5)
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_transient_logs_failure_discards_partial_output(self):
        seen = 0

        def flaky(argv, **kwargs):
            nonlocal seen
            if argv[1] == "logs":
                seen += 1
                if seen == 1:
                    self.calls.append(list(argv))
                    kwargs["stdout"].write("partial failed log\n")
                    return subprocess.CompletedProcess(argv, 125, b"")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=flaky):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(seen, 2)
        self.assertEqual(self.stdout.getvalue(), "micall.process_run(): Done.\n")
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_logs_timeout_discards_partial_output_and_fails_closed(self):
        def interrupted(argv, **kwargs):
            if argv[1] == "logs":
                self.calls.append(list(argv))
                kwargs["stdout"].write("partial unauthenticated log\n")
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=interrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (124, "logs"))
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)
        self.assertEqual(sum(c[1] == "logs" for c in self.calls), 1)
        self.assertEqual(self.calls[-1][1], "rm")

    def test_logs_io_error_discards_partial_output(self):
        def interrupted(argv, **kwargs):
            if argv[1] == "logs":
                self.calls.append(list(argv))
                kwargs["stdout"].write("partial unauthenticated log\n")
                raise OSError("lost Podman log stream")
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=interrupted):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (1, "logs"))
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)

    def test_metadata_has_stage_cap_but_micall_wait_keeps_full_budget(self):
        observed = []
        def recording(argv, **kwargs):
            observed.append((argv[1], kwargs["timeout"]))
            return self.fake(argv, **kwargs)
        with patch.object(lifecycle, "_run_command", side_effect=recording):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 0)
        self.assertEqual([stage for stage, _ in observed],
                         ["create", "start", "wait", "logs", "rm"])
        for stage, budget in observed:
            if stage == "wait":
                self.assertGreater(budget, lifecycle.CREATE_TIMEOUT_SECONDS)
            elif stage == "create":
                self.assertGreater(budget, lifecycle.METADATA_TIMEOUT_SECONDS)
                self.assertLessEqual(budget, lifecycle.CREATE_TIMEOUT_SECONDS)
            else:
                self.assertLessEqual(budget, lifecycle.METADATA_TIMEOUT_SECONDS)

    def test_create_timeout_still_obeys_remaining_whole_container_budget(self):
        observed = []
        def recording(argv, **kwargs):
            observed.append((argv[1], kwargs["timeout"]))
            return self.fake(argv, **kwargs)
        with patch.object(lifecycle, "_run_command", side_effect=recording):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 60)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(observed)
        self.assertLessEqual(observed[0][1], 60)
        self.assertGreater(observed[0][1], 0)

    def test_metadata_timeout_fails_closed_without_reexecuting(self):
        def timed_out(argv, **kwargs):
            if argv[1] == "create":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return self.fake(argv, **kwargs)
        with patch.object(lifecycle, "_run_command", side_effect=timed_out):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (124, "create"))
        self.assertIn("TimeoutExpired", self.stderr.getvalue())
        self.assertEqual(self.calls, [])

    def test_timed_out_create_reclaims_only_owned_container_name(self):
        # A real timed-out Podman create may have committed its name without
        # returning an ID. Never start MiCall; reclaim only our unique name.
        name = "ivanka-bench-ivanka-1793586776-32030-69942039"
        self.command[self.command.index("--name") + 1] = name

        def timed_out(argv, **kwargs):
            if argv[1] == "create":
                self.calls.append(list(argv))
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=timed_out):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (124, "create"))
        self.assertEqual([c[1] for c in self.calls], ["create", "rm"])
        self.assertEqual(self.calls[-1], ["podman", "rm", "--force", name])

    def test_timed_out_create_cleanup_keeps_original_deadline(self):
        name = "ivanka-bench-iva-1793586776-32030-69942039"
        self.command[self.command.index("--name") + 1] = name

        def timed_out(argv, **kwargs):
            self.calls.append(list(argv))
            if argv[1] == "create":
                time.sleep(0.04)
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=timed_out):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 0.01)
        self.assertEqual((result.returncode, result.stage), (124, "create"))
        self.assertEqual([c[1] for c in self.calls], ["create"])

    def test_emergency_cleanup_lock_wait_is_bounded(self):
        # A failed start used to wait up to the whole 1800-second deadline
        # just to acquire the emergency cleanup flock.
        self.exit["start"] = 125
        lock_deadlines = []

        @contextmanager
        def recording_lock(deadline):
            lock_deadlines.append(deadline)
            yield

        with patch.object(lifecycle, "transaction_lock", recording_lock):
            result = self.run_case()
        self.assertEqual((result.returncode, result.stage), (1, "start"))
        self.assertEqual(len(lock_deadlines), 3)  # create, start, cleanup
        self.assertLessEqual(lock_deadlines[-1] - time.monotonic(), 10.1)
        self.assertEqual(self.calls[-1][1], "rm")

    def test_emergency_cleanup_never_exceeds_sample_deadline(self):
        # Simulate a CLI timeout after creation. The old implementation
        # launched a fresh ten-second cleanup beyond the sample deadline.
        def slow_start(argv, **kwargs):
            if argv[1] == "start":
                self.calls.append(list(argv))
                time.sleep(0.15)
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return self.fake(argv, **kwargs)

        with patch.object(lifecycle, "_run_command", side_effect=slow_start):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 0.1)
        self.assertEqual((result.returncode, result.stage), (124, "start"))
        self.assertEqual([call[1] for call in self.calls], ["create", "start"])

    def test_deadline_does_not_launch(self):
        result = self.run_case(remaining=0)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(self.calls, [])

    def test_ambiguous_wait_rechecks_same_id_without_reexecuting(self):
        responses = iter((b"0\n0\n", b"0\n"))
        def fake(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, next(responses))
            return result
        with patch.object(lifecycle, "_run_command", side_effect=fake):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (0, "complete"))
        actions = [c[1] for c in self.calls]
        self.assertEqual(actions, ["create", "start", "wait", "wait",
                                   "logs", "rm"])
        self.assertEqual(self.calls[2], self.calls[3])
        self.assertIn("exact container wait", self.stderr.getvalue())

    def test_persistently_ambiguous_wait_fails_closed(self):
        def fake(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, b"0\n0\n")
            return result
        with patch.object(lifecycle, "_run_command", side_effect=fake):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual((result.returncode, result.stage), (1, "wait"))
        self.assertIn("sha256_prefix", self.stderr.getvalue())
        self.assertEqual(sum(c[1] == "start" for c in self.calls), 1)
        self.assertEqual(sum(c[1] == "wait" for c in self.calls), 3)
        self.assertEqual(self.calls[-1][1], "rm")
        self.assertEqual(self.stdout.getvalue(), "")

    def test_nonzero_micall_exit_is_preserved(self):
        def fake(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            if argv[1] == "wait":
                return subprocess.CompletedProcess(argv, 0, b"42\n")
            return result
        with patch.object(lifecycle, "_run_command", side_effect=fake):
            result = lifecycle.run_detached(
                self.command, self.stdout, self.stderr, 1800)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(self.calls[-1][1], "rm")


if __name__ == "__main__":
    unittest.main()
