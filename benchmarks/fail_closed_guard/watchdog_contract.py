"""Minimal integration contract between the watchdog, PX admission and P1.

These helpers are wired into the live launch, admission and receipt paths:
``launch.operate`` calls ``require_supported_mode`` before spawn, armed
admission uses ``require_watchdog_readiness`` to bind the watchdog's store and
a live kernel identity, and every final state passes through
``downgrade_on_watchdog_teardown`` before a receipt is written. The remaining
open item is deployment (s6 install, ``WATCHDOG_ARMED`` and operator arming),
which stays an explicit operator action; see
docs/bench/watchdog-p1-natural-exit-integration-20261126.md.
"""
import json
import math
import time
from pathlib import Path

from . import heartbeat, lease, watchdog
from .errors import GuardExceeded

SUPPORTED_MODES = ("pilot",)


def is_bound(path, graphroot):
    """True only when an ALIVE record names this exact watchdog store.

    The launcher does not necessarily inherit the s6 service environment, so
    the durable availability record is the authoritative signal that the
    independent observer is armed for this project.
    """
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        return False
    try:
        record = json.loads(source.read_text())
    except (OSError, ValueError):
        return False
    return (isinstance(record, dict)
            and record.get("schema") == heartbeat.ALIVE_SCHEMA
            and record.get("graphroot") == str(graphroot))


def require_watchdog_readiness(path, *, graphroot, wall=None, max_age=None,
                               snapshot=None):
    """Adapt a genuine watchdog ALIVE record to the PR505 readiness contract.

    Unlike raw `heartbeat.read_alive`, this binds readiness to the watchdog's
    own store namespace and to a live kernel task, so a stale record from a
    foreign graphroot or a reused PID cannot unblock admission.
    """
    clock = wall or time.time
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise GuardExceeded("watchdog_unavailable")
    try:
        record = json.loads(source.read_text())
    except (OSError, ValueError) as exc:
        raise GuardExceeded("watchdog_unavailable") from exc
    if (not isinstance(record, dict)
            or record.get("schema") != heartbeat.ALIVE_SCHEMA
            or record.get("graphroot") != str(graphroot)):
        raise GuardExceeded("watchdog_unbound")
    at = record.get("at_utc")
    if not isinstance(at, (int, float)) or not math.isfinite(at):
        raise GuardExceeded("watchdog_unavailable")
    age = clock() - at
    if age < 0 or not math.isfinite(age) or age > (max_age or heartbeat.ALIVE_MAX_AGE):
        raise GuardExceeded("watchdog_unavailable")
    pid, finger = record.get("pid"), record.get("fingerprint")
    if (not isinstance(pid, int) or pid <= 0
            or not isinstance(finger, list) or len(finger) != 2
            or not all(isinstance(value, int) and value > 0 for value in finger)):
        raise GuardExceeded("watchdog_unbound")
    if snapshot is not None:
        observed = snapshot().get(pid)
        if (observed is None
                or (observed.get("starttime"), observed.get("pid_ns")) != tuple(finger)):
            raise GuardExceeded("watchdog_unavailable")
    return {"source": str(source), "ready": True, "identity_bound": True,
            "pid_ns": finger[1], "starttime": finger[0],
            "schema": record["schema"]}


def durable_deadline(root, ident, wall_seconds):
    """Return the original lease deadline, never a restarted clock reading."""
    if wall_seconds <= 0:
        raise GuardExceeded("invalid_config")
    start = lease.acquisition_start(root, ident)
    if not isinstance(start, (int, float)) or not math.isfinite(start):
        raise GuardExceeded("invalid_lease")
    return start + min(wall_seconds, watchdog.DEFAULT_WALL_SECONDS)


def require_supported_mode(mode):
    """Fail closed for modes the independent watchdog cannot supervise."""
    if mode not in SUPPORTED_MODES:
        raise GuardExceeded("watchdog_unsupported_mode")


def downgrade_on_watchdog_teardown(root, ident, state):
    """A watchdog fail-closed teardown can never become a finished receipt."""
    events = [event for event in watchdog.read_evidence(root)
              if event.get("worker") == str(ident)
              and event.get("result") == "fail_closed"
              and event.get("action") == "teardown"]
    if not events:
        return state
    updated = dict(state)
    if updated.get("status") == "finished":
        updated["status"] = "failed"
        updated["reason"] = "watchdog_fail_closed"
    updated["watchdog_evidence"] = {
        "path": str(watchdog.evidence_path(root)),
        "events": [event.get("reason") for event in events]}
    return updated
