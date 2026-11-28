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

from . import binding, heartbeat, lease, watchdog
from .errors import GuardExceeded

# COPY-only overlay builds are supervised by the same watchdog through their
# exact session-leader process group; arbitrary "build" mode stays refused.
SUPPORTED_MODES = ("pilot", "copy_overlay")

# Only reasons the watchdog itself can fail closed with that are also valid
# receipt failure reasons may travel into a receipt. Every other observer fault
# keeps the generic downgrade: an unclassified fault must never become a
# scientific or recovery attribution.
ATTRIBUTABLE_WATCHDOG_REASONS = frozenset((
    "binding_unavailable", "measurement_unavailable", "identity_lost",
    "wall_limit", "observed_rss_limit",
))


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
    if isinstance(record, dict) and record.get("schema") == heartbeat.WITHDRAWN_SCHEMA:
        # The watchdog observed its own failed state; admission stays blocked
        # until a clean observation replaces this marker with a live record.
        raise GuardExceeded("watchdog_failed")
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


def _action_is_teardown(event):
    """Watchdog action may be a string or an object-shaped action record."""
    action = event.get("action")
    if isinstance(action, str):
        return action == "teardown"
    return isinstance(action, dict) and action.get("action") == "teardown"


def _event_cid(event):
    """The one full CID this teardown event names, or None when ambiguous."""
    for source in (event, event.get("action")):
        if not isinstance(source, dict):
            continue
        cid = source.get("cid")
        if isinstance(cid, str) and binding.CID.fullmatch(cid):
            return cid
    return None


def _proven_watchdog_reason(root, ident, events, state):
    """Return the single watchdog reason bound to this arm's exact CID proof.

    Attribution requires all of: the launcher's bound CID, a durable active
    lease binding that CID, a later lease release whose proof names that same
    CID, and one fail-closed teardown decision naming that CID after lease
    acquisition. A foreign or ambiguous CID, a decision without completed
    teardown, or an observer fault outside the attributable set yields None so
    the caller keeps only the generic downgrade.
    """
    bound = state.get("bound_cid")
    if not isinstance(bound, str) or not binding.CID.fullmatch(bound):
        return None
    try:
        journal = lease.events(root)
    except (OSError, ValueError, GuardExceeded):
        return None
    binds = [event for event in journal
             if event.get("lease") == str(ident)
             and event.get("state") == "active"
             and event.get("cid") == bound]
    releases = [event for event in journal
                if event.get("lease") == str(ident)
                and event.get("state") in lease.CLOSED
                and event.get("cid") == bound]

    def proof_names_cid(proof):
        if isinstance(proof, str):
            return proof == bound
        return isinstance(proof, dict) and bound in (
            proof.get("pilot_container_id"), proof.get("cid"))

    if not any(proof_names_cid(event.get("proof")) for event in releases):
        return None
    bind_times = [event["at_utc"] for event in binds
                  if isinstance(event.get("at_utc"), (int, float))]
    release_times = [event["at_utc"] for event in releases
                     if isinstance(event.get("at_utc"), (int, float))]
    if not bind_times or not release_times or min(release_times) <= max(bind_times):
        return None
    reasons = set()
    for event in events:
        cid = _event_cid(event)
        if cid is not None and cid != bound:
            return None  # a teardown of another container makes ownership ambiguous
        if cid is None:
            continue
        if event.get("lease_state") not in (None, "bound"):
            continue
        reason = event.get("reason")
        start, at = event.get("durable_start"), event.get("at_utc")
        if (isinstance(reason, str)
                and reason in ATTRIBUTABLE_WATCHDOG_REASONS
                and isinstance(start, (int, float))
                and isinstance(at, (int, float))
                and at >= start):
            reasons.add(reason)
    if len(reasons) != 1:
        return None
    return next(iter(reasons))


def downgrade_on_watchdog_teardown(root, ident, state):
    """A watchdog fail-closed teardown can never become a finished receipt.

    The observer's real reason travels into a future failure receipt only when
    its decision is bound to the exact CID this arm durably leased and then
    released with teardown proof. Foreign, ambiguous or undecided teardowns
    keep the generic downgrade. Nothing here rewrites an existing receipt or
    adds a retry.
    """
    events = [event for event in watchdog.read_evidence(root)
              if event.get("worker") == str(ident)
              and event.get("result") == "fail_closed"
              and _action_is_teardown(event)]
    if not events:
        return state
    updated = dict(state)
    if updated.get("status") == "finished":
        updated["status"] = "failed"
        updated["reason"] = "watchdog_fail_closed"
    updated["watchdog_evidence"] = {
        "path": str(watchdog.evidence_path(root)),
        "events": [event.get("reason") for event in events]}
    reason = _proven_watchdog_reason(root, ident, events, updated)
    if reason is not None:
        updated["reason"] = reason
        updated["watchdog_evidence"]["attributed_reason"] = reason
    return updated
