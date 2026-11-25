"""Minimal integration contract between the watchdog, PX admission and P1.

SOURCE-ONLY helpers preserved from deterministic review. They are intentionally
not wired into live launch/admission paths: build-mode refusal and receipt
downgrade are owner policy decisions recorded as unresolved in
docs/bench/watchdog-505-510-integration-20261125.md.
"""
import json
import math
import time
from pathlib import Path

from . import heartbeat, lease, watchdog
from .errors import GuardExceeded

SUPPORTED_MODES = ("pilot",)


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
