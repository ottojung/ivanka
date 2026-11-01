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
    return bool(tail and not any("micall.process_run(): Done." in line for line in tail)
                and (tail[-1] in _STARTUP_LOCK_ERRORS
                     or (len(tail) == 1 and _PRESTART_SAVE_LOCK.fullmatch(tail[0]))))
