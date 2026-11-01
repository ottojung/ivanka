"""CPU-only concurrency and deadline invariants for detached Podman lifecycle."""
import io
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import podman_detached_lifecycle as lifecycle


class LifecycleConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        lock = Path(self.tmp.name) / "podman.lock"
        p = patch.object(lifecycle, "LIFECYCLE_LOCK", lock)
        p.start()
        self.addCleanup(p.stop)

    def test_lifecycle_transactions_serialize_but_waits_overlap(self):
        state_lock = threading.Lock()
        state = {"metadata": 0, "max_metadata": 0,
                 "waits": 0, "max_waits": 0}
        both_waiting = threading.Event()
        release_waits = threading.Event()
        results = []
        errors = []

        def fake(argv, *, stdout, stderr, timeout, check):
            stage = argv[1]
            if stage in ("create", "start", "rm"):
                with state_lock:
                    state["metadata"] += 1
                    state["max_metadata"] = max(
                        state["max_metadata"], state["metadata"])
                time.sleep(0.015)
                with state_lock:
                    state["metadata"] -= 1
            if stage == "wait":
                with state_lock:
                    state["waits"] += 1
                    state["max_waits"] = max(state["max_waits"], state["waits"])
                    if state["waits"] == 2:
                        both_waiting.set()
                if not release_waits.wait(5):
                    raise RuntimeError("waits were accidentally serialized")
                with state_lock:
                    state["waits"] -= 1
            if stage == "logs":
                stdout.write("micall.process_run(): Done.\n")
            data = b"b" * 64 if stage == "create" else (
                b"0\n" if stage == "wait" else b"")
            return subprocess.CompletedProcess(argv, 0, data)

        def worker(i):
            try:
                cmd = ["podman", "run", "--rm", "--name", f"worker-{i}",
                       "a" * 64, "micall"]
                result = lifecycle.run_detached(
                    cmd, io.StringIO(), io.StringIO(), 10)
                results.append(result.returncode)
            except Exception as exc:
                errors.append(exc)

        with patch.object(lifecycle.subprocess, "run", side_effect=fake):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for thread in threads:
                thread.start()
            try:
                self.assertTrue(both_waiting.wait(5),
                                "MiCall waits must be concurrent")
            finally:
                release_waits.set()
                for thread in threads:
                    thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(errors, errors)
        self.assertEqual(sorted(results), [0, 0])
        self.assertEqual(state["max_metadata"], 1)
        self.assertEqual(state["max_waits"], 2)

    def test_contended_lock_expires_without_podman_create(self):
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with lifecycle.transaction_lock(time.monotonic() + 5):
                entered.set()
                release.wait(5)

        thread = threading.Thread(target=holder)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            cmd = ["podman", "run", "--rm", "--name", "locked",
                   "a" * 64, "micall"]
            with patch.object(lifecycle.subprocess, "run") as run:
                result = lifecycle.run_detached(
                    cmd, io.StringIO(), io.StringIO(), 0.05)
            self.assertEqual(result.returncode, 124)
            run.assert_not_called()
        finally:
            release.set()
            thread.join(5)


if __name__ == "__main__":
    unittest.main()
