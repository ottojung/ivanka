"""Experimental short-locked Podman lifecycle for concurrent MiCall workers.

Only create/start/remove acquire the shared transaction lock. Container execution
and waiting remain parallel. Every step consumes the original sample wall budget.
Failures after creation are never interpreted as safe-to-retry startup failures.
"""
from __future__ import annotations

import fcntl
import os
import re
import signal
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



def _run_command(argv, *, stdout, stderr, timeout, check=False):
    """Kill the entire owned Podman CLI group after a stage timeout.

    Podman forks a helper that may outlive subprocess.run()'s direct-child
    kill. The new session contains only this stage's processes, never the
    running benchmark worker or another container's Podman transaction.
    """
    if check:
        raise ValueError("Podman lifecycle stage must inspect exit status")
    child = subprocess.Popen(
        argv, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        output, _ = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # Podman command arguments can contain an entire Python verifier
        # script. Never print that script just to report a timed-out stage.
        raise subprocess.TimeoutExpired(argv[:2], timeout)
    return subprocess.CompletedProcess(argv, child.returncode, output)

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
    create_name = command[command.index("--name") + 1]
    timed_out_create = False
    failed_create_without_id = False

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
                return _run_command(argv, stdout=output or subprocess.PIPE,
                                      stderr=stderr, timeout=budget_for_stage(),
                                      check=False)
        return _run_command(argv, stdout=output or subprocess.PIPE,
                              stderr=stderr, timeout=budget_for_stage(),
                              check=False)

    def retry_read_or_remove(argv, *, lock=False, output=None):
        # Waiting, reading logs, and removing never restart MiCall.
        # A timed-out rm can actually finish before its CLI reports back.
        # Only an exact-ID Podman absence check can establish that cleanup
        # succeeded; a nonzero rm alone must never count as success.
        remove_timed_out = False

        def confirmed_removed():
            try:
                probe = call(["podman", "container", "exists", cid], lock=True)
            except (subprocess.TimeoutExpired, TimeoutError, OSError, ValueError):
                return False
            # Podman container exists: 0=present, 1=absent, 125=error.
            return probe.returncode == 1
        # Failed logs may have emitted a partial prefix: discard it before
        # retrying so one container's output is never duplicated.
        for attempt in range(4):
            offset = output.tell() if output is not None else None

            def discard_partial_output(offset=offset):
                if offset is not None:
                    output.seek(offset)
                    output.truncate()
                    output.flush()

            try:
                result = call(argv, lock=lock, output=output)
            except (subprocess.TimeoutExpired, TimeoutError, OSError, ValueError) as exc:
                # A timed-out Podman CLI can already have written part of its
                # logs. They must not survive as completion evidence.
                discard_partial_output()
                # An authentic S97 MiCall run completed, but its first rm CLI
                # exceeded the 120s metadata cap with ample sample time left.
                # Retry ONLY removal of the same immutable container ID.
                # Never rerun MiCall, and never accept an unverified cleanup.
                if argv[1] == "rm" and isinstance(
                        exc, (subprocess.TimeoutExpired, TimeoutError)):
                    remove_timed_out = True
                    if confirmed_removed():
                        return subprocess.CompletedProcess(argv, 0)
                    if attempt < 3 and time.monotonic() + 0.2 < deadline:
                        stderr.write("Benchmark: Podman rm timed out; retrying same container ID\n")
                        stderr.flush()
                        time.sleep(0.2)
                        continue
                raise
            if result.returncode == 0:
                return result
            discard_partial_output()
            if argv[1] == "rm" and remove_timed_out and confirmed_removed():
                return subprocess.CompletedProcess(argv, 0)
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
            elif not response:
                # Podman may commit the name, then fail before printing an ID.
                failed_create_without_id = True
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
        if stage == "create" and isinstance(exc, subprocess.TimeoutExpired):
            timed_out_create = True
        stderr.write(("Benchmark: detached Podman " + stage + " failure: " +
                      type(exc).__name__ + ": " + str(exc) + "\n"))
        stderr.flush()
        # Never claim success after an ambiguous start, wait, or removal.
        return SimpleNamespace(returncode=124 if isinstance(
            exc, (TimeoutError, subprocess.TimeoutExpired)) else 1, stage=stage)
    finally:
        cleanup_target = cid
        # A timed-out or failed create can leave a named but ID-less container.
        # Only reclaim this invocation's uniquely generated benchmark name;
        # never remove an arbitrary caller-supplied container by name.
        if cleanup_target is None and (timed_out_create or failed_create_without_id) and re.fullmatch(
                r"ivanka-bench-(?:iva|ivanka)-[0-9]+-[0-9]+-[0-9a-f]{8}(?:-dbretry[0-9]+)?",
                create_name):
            cleanup_target = create_name
        if cleanup_target is not None:
            # Best effort only. Cleanup does not turn a failed arm into success.
            # The original whole-container deadline also bounds emergency
            # cleanup. A failed arm must never silently spend extra time
            # outside its frozen sample allowance.
            if time.monotonic() < deadline:
                # Bound lock acquisition AND removal together, not merely
                # the subprocess: a contended flock must not consume the
                # remaining 28 minutes of a failed sample.
                cleanup_deadline = min(deadline, time.monotonic() + 10)
                try:
                    with transaction_lock(cleanup_deadline):
                        budget = cleanup_deadline - time.monotonic()
                        if budget > 0:
                            _run_command(["podman", "rm", "--force", cleanup_target],
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL,
                                           timeout=budget, check=False)
                except (TimeoutError, OSError, subprocess.TimeoutExpired):
                    pass
