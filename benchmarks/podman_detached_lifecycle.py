"""Experimental short-locked Podman lifecycle for concurrent MiCall workers.

Only create/start/remove acquire the shared transaction lock. Container execution
and waiting remain parallel. Every step consumes the original sample wall budget.
Failures after creation are never interpreted as safe-to-retry startup failures.
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

LIFECYCLE_LOCK = Path(os.environ.get(
    "IVANKA_PODMAN_LIFECYCLE_LOCK", "/workspace/ivanka-podman-lifecycle.lock"))


@contextmanager
def transaction_lock(deadline: float):
    LIFECYCLE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LIFECYCLE_LOCK.open("a+b") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Podman transaction lock exceeded sample deadline")
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run_detached(command: list[str], stdout, stderr, remaining: float):
    """Return a subprocess-like result. No successful exit without wait+logs+rm."""
    # The benchmark emits --rm as the first Podman option.  Do not remove
    # identical strings from the image's argv: that would alter MiCall inputs.
    if command[:3] != ["podman", "run", "--rm"] or "--name" not in command:
        raise ValueError("Expected pinned podman run --rm command")
    deadline = time.monotonic() + remaining
    create = ["podman", "create", *command[3:]]
    cid = None
    stage = "create"

    def call(argv, *, output=None, lock=False):
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("Whole-container deadline exceeded")
        if lock:
            with transaction_lock(deadline):
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise TimeoutError("Whole-container deadline exceeded")
                return subprocess.run(argv, stdout=output or subprocess.PIPE,
                                      stderr=stderr, timeout=budget, check=False)
        return subprocess.run(argv, stdout=output or subprocess.PIPE,
                              stderr=stderr, timeout=budget, check=False)

    def retry_read_or_remove(argv, *, lock=False, output=None):
        # Waiting, reading logs, and removing never restart MiCall.
        # Failed logs may have emitted a partial prefix: discard it before
        # retrying so one container's output is never duplicated.
        for attempt in range(4):
            offset = output.tell() if output is not None else None
            result = call(argv, lock=lock, output=output)
            if result.returncode == 0:
                return result
            if offset is not None:
                output.seek(offset)
                output.truncate()
                output.flush()
            if attempt < 3 and time.monotonic() + 0.2 < deadline:
                time.sleep(0.2)
        return result

    try:
        created = call(create, lock=True)
        if created.returncode:
            # Only a completely empty create response may be retried by the
            # existing exact prestart-lock classifier. A partial container ID
            # makes startup provenance ambiguous: fail closed.
            return SimpleNamespace(
                returncode=created.returncode if not created.stdout.strip() else 1,
                stage=stage)
        cid = created.stdout.decode().strip()
        if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid):
            raise ValueError("Podman create returned no immutable container ID")
        stage = "start"
        started = call(["podman", "start", cid], lock=True)
        if started.returncode:
            raise RuntimeError("Podman start failed after container creation")
        stage = "wait"
        waited = retry_read_or_remove(["podman", "wait", cid])
        if waited.returncode:
            raise RuntimeError("Podman wait failed after container start")
        try:
            container_exit = int(waited.stdout.decode().strip())
        except ValueError as exc:
            raise RuntimeError("Podman wait returned invalid exit status") from exc
        if not 0 <= container_exit <= 255:
            raise RuntimeError("Podman wait returned invalid exit status")
        stage = "logs"
        logged = retry_read_or_remove(["podman", "logs", cid], output=stdout)
        if logged.returncode:
            raise RuntimeError("Cannot authenticate completed container logs")
        stage = "remove"
        removed = retry_read_or_remove(["podman", "rm", cid], lock=True)
        if removed.returncode:
            raise RuntimeError("Podman explicit removal failed")
        cid = None
        return SimpleNamespace(returncode=container_exit, stage="complete")
    except (subprocess.TimeoutExpired, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        stderr.write(("Benchmark: detached Podman " + stage + " failure: " +
                      type(exc).__name__ + ": " + str(exc) + "\n"))
        stderr.flush()
        # Never claim success after an ambiguous start, wait, or removal.
        return SimpleNamespace(returncode=124 if isinstance(
            exc, (TimeoutError, subprocess.TimeoutExpired)) else 1, stage=stage)
    finally:
        if cid is not None:
            # Best effort only. Cleanup does not turn a failed arm into success.
            try:
                with transaction_lock(time.monotonic() + 10):
                    subprocess.run(["podman", "rm", "--force", cid],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, check=False)
            except (TimeoutError, OSError, subprocess.TimeoutExpired):
                pass
