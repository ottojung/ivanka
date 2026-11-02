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
# Metadata operations must not monopolize the shared lock for the entire
# 1800-second sample budget. Waiting for MiCall retains the full remainder.
METADATA_TIMEOUT_SECONDS = 120.0
# Authentic S85 timed out during Podman create at the metadata cap with
# ~1660s still available under the unchanged 1800s whole-container deadline.
# Give creation a bounded second window; other metadata stages stay at 120s.
CREATE_TIMEOUT_SECONDS = 240.0


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
        def budget_for_stage():
            remaining_budget = deadline - time.monotonic()
            if remaining_budget <= 0:
                raise TimeoutError("Whole-container deadline exceeded")
            if argv[1] == "wait":
                return remaining_budget
            stage_cap = (CREATE_TIMEOUT_SECONDS if argv[1] == "create"
                         else METADATA_TIMEOUT_SECONDS)
            return min(remaining_budget, stage_cap)

        if lock:
            with transaction_lock(deadline):
                return subprocess.run(argv, stdout=output or subprocess.PIPE,
                                      stderr=stderr, timeout=budget_for_stage(),
                                      check=False)
        return subprocess.run(argv, stdout=output or subprocess.PIPE,
                              stderr=stderr, timeout=budget_for_stage(),
                              check=False)

    def retry_read_or_remove(argv, *, lock=False, output=None):
        # Waiting, reading logs, and removing never restart MiCall.
        # Failed logs may have emitted a partial prefix: discard it before
        # retrying so one container's output is never duplicated.
        for attempt in range(4):
            offset = output.tell() if output is not None else None

            def discard_partial_output():
                if offset is not None:
                    output.seek(offset)
                    output.truncate()
                    output.flush()

            try:
                result = call(argv, lock=lock, output=output)
            except (subprocess.TimeoutExpired, TimeoutError, OSError, ValueError):
                # A timed-out Podman CLI can already have written part of its
                # logs. They must not survive as completion evidence.
                discard_partial_output()
                raise
            if result.returncode == 0:
                return result
            discard_partial_output()
            if attempt < 3 and time.monotonic() + 0.2 < deadline:
                time.sleep(0.2)
        return result

    try:
        created = call(create, lock=True)
        if created.returncode:
            # A failed create with a complete ID may have left a container.
            # Never retry startup, but best-effort cleanup that exact ID.
            # Other nonempty output remains ambiguous and fails closed.
            response = created.stdout.decode(errors="replace").strip()
            if len(response) == 64 and all(c in "0123456789abcdef" for c in response):
                cid = response
            return SimpleNamespace(
                returncode=created.returncode if not response else 1,
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
            # The original whole-container deadline also bounds emergency
            # cleanup. A failed arm must never silently spend extra time
            # outside its frozen sample allowance.
            if time.monotonic() < deadline:
                try:
                    with transaction_lock(deadline):
                        budget = deadline - time.monotonic()
                        if budget > 0:
                            subprocess.run(["podman", "rm", "--force", cid],
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL,
                                           timeout=min(10, budget), check=False)
                except (TimeoutError, OSError, subprocess.TimeoutExpired):
                    pass
