"""Authenticate MiCall completion when Podman alone fails removing a completed container.

Never infer success from a generic nonzero exit or from final output files alone.
The exact auto-removal database-lock diagnostic and MiCall's independent
in-container monotonic completion record must BOTH be present.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

TIMING_ORIGIN = "micall_in_container_monotonic_v1"
_POSTRUN_LOCK = re.compile(
    r'time="[^"\r\n]+" level=error msg="Removing container '
    r'(?P<id>[0-9a-f]{64}): retrieving container (?P=id) '
    r'configuration from DB to remove: retrieving container (?P=id) '
    r'config from DB: database is locked"'
)

# Podman can also fail while saving the state of a container it has already
# unmounted. Match the entire diagnostic and the SAME container ID throughout.
_POSTRUN_SAVE_LOCK = re.compile(
    r'time="[^"\r\n]+" level=error msg="Removing container '
    r'(?P<id>[0-9a-f]{64}): cleaning up container (?P=id): '
    r'unmounting container (?P=id) storage: unmounting container (?P=id): '
    r'saving container (?P=id) state: beginning container (?P=id) '
    r'save transaction: database is locked"'
)
_PRESTART_SAVE_LOCK = re.compile(
    r'Error: saving container (?P<id>[0-9a-f]{64}) state: '
    r'beginning container (?P=id) save transaction: database is locked'
)


def cleanup_lock_after_micall_done(stderr_file: Path) -> bool:
    """Require the actual Podman auto-removal error AFTER MiCall completion."""
    try:
        with stderr_file.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 16384))
            ending = handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return False
    before, newline, last = ending.rpartition("\n")
    return bool(
        newline
        and (_POSTRUN_LOCK.fullmatch(last) or _POSTRUN_SAVE_LOCK.fullmatch(last))
        and "micall.process_run(): Done." in before
    )


def verified_internal_seconds(timing_file: Path, container_wall_seconds: float) -> float:
    """Validate the same timer/cap conditions as ordinary successful arms."""
    record = json.loads(timing_file.read_text())
    seconds = record["seconds"]
    if (
        record.get("timing_origin") != TIMING_ORIGIN
        or record.get("exit_code") != 0
        or not isinstance(seconds, (float, int))
        or isinstance(seconds, bool)
        or not math.isfinite(seconds)
        or not isinstance(container_wall_seconds, (float, int))
        or not math.isfinite(container_wall_seconds)
        or not 0 < seconds <= container_wall_seconds + 1
    ):
        raise ValueError("Invalid in-container MiCall measurement")
    return float(seconds)


def authenticated_postrun_cleanup(raw_exit: int, folder: Path, wall_seconds: float) -> float | None:
    """Return independently measured seconds ONLY for the exact cleanup failure."""
    if raw_exit != 127 or not cleanup_lock_after_micall_done(folder / "podman.stderr.log"):
        return None
    try:
        return verified_internal_seconds(folder / "micall_internal_timing.json", wall_seconds)
    except (OSError, KeyError, ValueError, TypeError):
        return None


def no_micall_output(folder: Path) -> bool:
    """Do not retry a Podman startup if MiCall may already have executed.

    A genuine prestart database lock leaves only the harness-created empty
    stdout/stderr logs and bad_cycles.csv. Any other output is evidence
    against assuming that retrying is side-effect-free.
    """
    expected = {"bad_cycles.csv", "podman.stdout.log", "podman.stderr.log"}
    try:
        if (folder / "podman.stdout.log").stat().st_size:
            return False
        return all(path.is_file() and path.name in expected
                   for path in folder.iterdir())
    except OSError:
        return False

_STARTUP_LOCK_ERRORS = frozenset((
    "Error: beginning transaction: database is locked",
    "Error: beginning container create transaction: database is locked",
))


def startup_database_lock(stderr_file: Path) -> bool:
    """Only retry Podman failures that occurred before MiCall even started."""
    try:
        tail = stderr_file.read_text(errors="replace").rstrip().splitlines()
    except OSError:
        return False
    # Logs from earlier failed starts are retained in the same file. Allow
    # only previous recognized pre-start errors and our own retry markers;
    # never treat arbitrary MiCall output as a pre-start-only failure.
    retry_marker = re.compile(r"Benchmark: retrying Podman startup after DB lock \(\d+\)")
    def prestart_line(line: str) -> bool:
        return bool(line in _STARTUP_LOCK_ERRORS
                    or _PRESTART_SAVE_LOCK.fullmatch(line)
                    or retry_marker.fullmatch(line))
    return bool(tail and all(prestart_line(line) for line in tail)
                and (tail[-1] in _STARTUP_LOCK_ERRORS
                     or _PRESTART_SAVE_LOCK.fullmatch(tail[-1])))



def podman_attempt_diagnostics(
    stderr_file: Path, start_offset: int, end_offset: int | None = None
) -> list[str]:
    """Extract Podman CLI errors for ONE attempt, never MiCall progress logs.

    The combined stderr log contains earlier failed startups and later MiCall
    progress; its final 1200 characters alone can hide the actual Podman error.
    This is diagnostic only and never changes acceptance or retry decisions.
    """
    try:
        with stderr_file.open("rb") as handle:
            handle.seek(0, 2)
            actual_end = handle.tell()
            end = actual_end if end_offset is None else min(end_offset, actual_end)
            if not 0 <= start_offset <= end:
                return []
            if end - start_offset <= 65536:
                handle.seek(start_offset)
                data = handle.read(end - start_offset)
            else:
                # Avoid loading large MiCall progress logs just to diagnose Podman.
                handle.seek(start_offset)
                beginning = handle.read(4096)
                handle.seek(end - 16384)
                data = beginning + b"\n" + handle.read(16384)
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    errors = [line.strip() for line in lines
              if line.startswith("Error:") or " level=error msg=" in line]
    return [line[:600] for line in errors[-3:]]
