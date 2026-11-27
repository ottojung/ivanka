"""Durable worker lease journal and read-only startup orphan reconciliation.

An advisory lock only protects a live launcher. If the launcher dies after it
spawns a container but before teardown is proven, the lock is released while
the container is still alive. This journal makes ownership durable: a lease is
appended before spawn and closed only after teardown proof. Startup
reconciliation never signals or removes a container; it refuses admission while
any prior owned resource is alive, leaving teardown with its owner.

Ownership is enforced, not merely recorded: older journals without an explicit
``owner`` treat the lease identifier as the owner (backward compatible), and a
foreign release (wrong owner or wrong CID) never closes a lease. This is what
keeps a dead controller's lease open so admission still fails closed.
"""
import json
import os
import time
from pathlib import Path

from . import binding, heartbeat, proc
from .errors import GuardExceeded, OrphanLease

SCHEMA = "ivanka.worker-lease.v1"
REPORT_SCHEMA = "ivanka.worker-lease.reconciliation.v1"
JOURNAL_NAME = ".worker-lease.jsonl"
CLOSED = ("released", "reconciled")


def _command(argv, env, timeout=15):
    return binding.command(argv, env, timeout=timeout)


def path(root):
    """Return the project-owned journal path (never caller controlled)."""
    return Path(root) / JOURNAL_NAME


def append(root, event):
    """Append one fsynced event; history is never rewritten or truncated."""
    fd = os.open(path(root), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True, default=str) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def events(root):
    """Return the validated journal, failing closed on tamper or corruption."""
    journal = path(root)
    if not journal.exists() and not journal.is_symlink():
        return []
    if journal.is_symlink() or not journal.is_file():
        raise GuardExceeded("journal_unavailable")
    table = []
    for line in journal.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            raise GuardExceeded("journal_unreadable")
        table.append(event)
    return table


def _owner_of(event):
    """Owner identity; legacy journals used the lease id as the owner."""
    owner = event.get("owner")
    return owner if owner is not None else event.get("lease")


def _matches(close_event, active_event):
    """A close is authorized only for the same owner and the same CID."""
    if _owner_of(close_event) != _owner_of(active_event):
        return False
    close_cid = close_event.get("cid")
    active_cid = active_event.get("cid")
    if close_cid is not None and active_cid is not None:
        return close_cid == active_cid
    return True


def latest(table):
    """Last event per lease wins; the journal remains append-only evidence.

    Close events from a foreign owner (or a foreign CID) are ignored, so a
    cross-owner release can never close a lease it does not own.
    """
    result = {}
    for event in table:
        lease = event.get("lease")
        if lease is None:
            continue
        if event.get("state") in CLOSED:
            active = result.get(lease)
            if active is None or active.get("state") in CLOSED:
                continue
            if not _matches(event, active):
                continue
        result[lease] = event
    return result


def acquire(root, ident, mode, *, owner=None, cidfile=None, cid=None):
    """Durably record ownership before any process or container is spawned.

    A caller that already knows the exact CID (the P1 harness binds it before
    sampling) may record it at acquire time instead of supplying a transient
    cidfile; reconciliation still uses only the append-only journal.
    """
    if mode not in ("pilot", "build", "copy_overlay") or (
            mode == "pilot" and cidfile is None and cid is None):
        raise GuardExceeded("invalid_lease")
    if cid is not None and (not isinstance(cid, str) or
                            not binding.CID.fullmatch(cid)):
        raise GuardExceeded("invalid_lease")
    event = {"schema": SCHEMA, "lease": str(ident), "owner": str(owner or ident),
             "state": "active", "mode": mode, "cid": cid,
             "cidfile": str(cidfile) if cidfile is not None else None,
             "pid": None, "fingerprint": None, "at_utc": time.time()}
    append(root, event)
    return event


def acquisition_start(root, ident):
    """Return the durable start recorded before spawn, never a later bind time."""
    start = None
    for event in events(root):
        if (event.get("lease") == str(ident)
                and event.get("state") == "active"
                and event.get("mode") in ("pilot", "build", "copy_overlay")
                and event.get("at_utc") is not None):
            start = event["at_utc"]
    return start


def bind(root, ident, pid, fingerprint=None, *, owner=None):
    """Attach build-process identity after spawn; before spawn it is unknown."""
    start = acquisition_start(root, ident)
    event = {"schema": SCHEMA, "lease": str(ident), "owner": str(owner or ident),
             "state": "active", "mode": "build", "cid": None, "cidfile": None,
             "pid": int(pid), "fingerprint": list(fingerprint) if fingerprint else None,
             "at_utc": time.time() if start is None else start}
    append(root, event)
    return event


def bind_group(root, ident, pid, pgid, fingerprint, *, owner=None,
               plan_sha256=None, graphroot=None, helper=False,
               baseline_ids=None, base_image=None, base_layers=None,
               storage_conf_sha256=None):
    """Bind the exact session leader and process group of a COPY-only build."""
    pid, pgid = int(pid), int(pgid)
    if pid <= 0 or pgid != pid or not isinstance(fingerprint, (list, tuple)) \
            or len(fingerprint) < 2:
        raise GuardExceeded("invalid_lease")
    start = acquisition_start(root, ident)
    event = {"schema": SCHEMA, "lease": str(ident),
             "owner": str(owner or ident), "state": "active",
             "mode": "copy_overlay", "cid": None, "cidfile": None,
             "pid": pid, "pgid": pgid, "fingerprint": list(fingerprint),
             "plan_sha256": plan_sha256, "graphroot": str(graphroot),
             "helper": bool(helper),
             "baseline_ids": sorted(baseline_ids or []),
             "base_image": base_image, "base_layers": list(base_layers or []),
             "storage_conf_sha256": storage_conf_sha256,
             "at_utc": time.time() if start is None else start}
    append(root, event)
    return event


def bind_cid(root, ident, cid, *, owner=None, cidfile=None, pid=None,
             fingerprint=None):
    """Durably record the exact pilot CID at the moment it is bound.

    The cidfile is transient (--rm deletes it on natural completion), but the
    journal is append-only evidence of ownership. Reconciliation and cleanup
    therefore use this CID and never need the file again.
    """
    if not isinstance(cid, str) or not binding.CID.fullmatch(cid):
        raise GuardExceeded("invalid_lease")
    start = acquisition_start(root, ident)
    event = {"schema": SCHEMA, "lease": str(ident), "owner": str(owner or ident),
             "state": "active", "mode": "pilot", "cid": cid,
             "cidfile": str(cidfile) if cidfile is not None else None,
             "pid": int(pid) if pid is not None else None,
             "fingerprint": list(fingerprint) if fingerprint else None,
             "at_utc": time.time() if start is None else start}
    append(root, event)
    return event


def release(root, ident, *, owner=None, cid=None, proof=None):
    """Close a lease only after authorized owner/CID match and teardown proof."""
    active = latest(events(root)).get(str(ident))
    if active is None or active.get("state") in CLOSED:
        raise GuardExceeded("lease_not_active")
    expected_owner = _owner_of(active)
    caller_owner = str(owner or ident)
    if caller_owner != expected_owner:
        raise GuardExceeded("unauthorized_release")
    active_cid = active.get("cid")
    if cid is not None and active_cid is not None and cid != active_cid:
        raise GuardExceeded("unauthorized_release")
    event = {"schema": SCHEMA, "lease": str(ident), "owner": caller_owner,
             "state": "released", "cid": cid if cid is not None else active_cid,
             "proof": proof, "at_utc": time.time()}
    append(root, event)
    return event


def _cid_for(event):
    cid = event.get("cid")
    if cid is None and event.get("cidfile"):
        try:
            cid = binding.read_cid(event["cidfile"])
        except GuardExceeded:
            return None
    return cid if isinstance(cid, str) and binding.CID.fullmatch(cid) else None


def report(blocked, closed, **extra):
    result = {"schema": REPORT_SCHEMA, "blocked": blocked, "closed": closed,
              "enforcement": "userspace_observed", "kernel_enforcement": False}
    result.update(extra)
    return result


def reconcile(root, env, *, command=None, snapshot=None):
    """Report active leases whose owned resource is still alive or unknown.

    Read-only with respect to containers. Absent resources are recorded as
    closed only when no lease blocks admission, so a failed check never
    silently mutates ownership state. A foreign release is never honored.
    """
    command = command or _command
    snapshot = snapshot or proc.snapshot
    try:
        active = {key: event for key, event in latest(events(root)).items()
                  if event.get("state") not in CLOSED}
    except (OSError, ValueError, TypeError, GuardExceeded) as exc:
        reason = exc.reason if isinstance(exc, GuardExceeded) else "journal_unreadable"
        return report([{"reason": reason, "detail": str(exc)[:200]}], [])

    blocked, closed = [], []
    pilots = [event for event in active.values() if event.get("mode") == "pilot"]
    listed = None
    if pilots:
        try:
            listed = set(command(
                ["podman", "ps", "-a", "--no-trunc", "--format", "{{.ID}}"],
                env).splitlines())
        except Exception as exc:
            blocked.append({"reason": "liveness_unknown",
                            "detail": str(exc)[:200]})

    for key, event in sorted(active.items()):
        lease_id = event.get("lease", key)
        if event.get("mode") == "pilot":
            if listed is None:
                blocked.append({"lease": lease_id, "reason": "liveness_unknown"})
                continue
            cid = _cid_for(event)
            if cid is None:
                blocked.append({"lease": lease_id,
                                "reason": "ambiguous_or_missing_cid"})
            elif cid in listed:
                blocked.append({"lease": lease_id, "cid": cid,
                                "reason": "orphan_container_alive"})
            else:
                closed.append({"lease": lease_id, "cid": cid,
                               "owner": _owner_of(event),
                               "reason": "proven_absent"})
            continue
        if event.get("mode") == "copy_overlay":
            try:
                table = snapshot()
            except Exception as exc:
                blocked.append({"lease": lease_id, "reason": "liveness_unknown",
                                "detail": str(exc)[:200]})
                continue
            finger = event.get("fingerprint")
            pgid = event.get("pgid")
            if (not isinstance(finger, (list, tuple)) or len(finger) < 3
                    or not isinstance(pgid, int) or pgid <= 0
                    or pgid != event.get("pid")):
                blocked.append({"lease": lease_id, "reason": "ambiguous_lease"})
                continue
            matches = [pid for pid, record in table.items()
                       if (record.get("starttime"), record.get("pid_ns"),
                           record.get("cmdline_sha")) == tuple(finger)]
            if len(matches) > 1:
                blocked.append({"lease": lease_id,
                                "reason": "ambiguous_identity"})
            elif len(matches) == 1:
                record = table[matches[0]]
                if record.get("pgid") != pgid:
                    blocked.append({"lease": lease_id,
                                    "reason": "orphan_process_alive",
                                    "detail": "process group changed"})
                else:
                    blocked.append({"lease": lease_id, "pid": matches[0],
                                    "pgid": pgid,
                                    "reason": "orphan_process_alive"})
            elif event.get("pid") in table:
                # The bound PID still exists but its kernel identity changed:
                # PID reuse is never equivalent to a proven-absent resource.
                blocked.append({"lease": lease_id, "pid": event["pid"],
                                "reason": "identity_lost"})
            else:
                closed.append({"lease": lease_id, "reason": "proven_absent",
                               "owner": _owner_of(event)})
            continue
        if event.get("mode") == "build":
            try:
                table = snapshot()
            except Exception as exc:
                blocked.append({"lease": lease_id, "reason": "liveness_unknown",
                                "detail": str(exc)[:200]})
                continue
            finger = event.get("fingerprint")
            if finger:
                matches = [pid for pid, record in table.items()
                           if (record.get("starttime"), record.get("pid_ns"),
                               record.get("cmdline_sha")) == tuple(finger)]
                if len(matches) > 1:
                    blocked.append({"lease": lease_id,
                                    "reason": "ambiguous_identity"})
                elif len(matches) == 1:
                    blocked.append({"lease": lease_id, "pid": matches[0],
                                    "reason": "orphan_process_alive"})
                else:
                    closed.append({"lease": lease_id, "reason": "proven_absent",
                                   "owner": _owner_of(event)})
            elif event.get("pid") is not None:
                record = table.get(event["pid"])
                if record is None:
                    closed.append({"lease": lease_id, "reason": "proven_absent",
                                   "owner": _owner_of(event)})
                elif any(record.get(k) is None for k in
                         ("starttime", "pid_ns", "cmdline_sha")):
                    blocked.append({"lease": lease_id, "reason": "liveness_unknown"})
                else:
                    blocked.append({"lease": lease_id, "pid": event["pid"],
                                    "reason": "orphan_process_alive"})
            else:
                blocked.append({"lease": lease_id, "reason": "ambiguous_lease"})
            continue
        blocked.append({"lease": lease_id, "reason": "invalid_lease"})

    if not blocked:
        for item in closed:
            append(root, {"schema": SCHEMA, "lease": item["lease"],
                          "owner": item.get("owner", item["lease"]),
                          "state": "reconciled", "reason": item["reason"],
                          "at_utc": time.time()})
    return report(blocked, closed)


def require_clear(root, env, *, watchdog_path=None,
                  watchdog_max_age=heartbeat.ALIVE_MAX_AGE, wall=None,
                  graphroot=None, snapshot=None, **kwargs):
    """Fail closed if a prior resource is alive or no watchdog is observing.

    An independent observer is a precondition for admission: without it a
    crashed controller could leave an owned container alive unnoticed. When
    ``graphroot`` is supplied (the armed-watchdog contract) readiness is also
    bound to the watchdog's own store namespace and to a live kernel task, so
    a foreign-namespace or PID-reused record cannot unblock admission.
    """
    if watchdog_path is not None:
        try:
            if graphroot is not None:
                from . import watchdog_contract
                watchdog_contract.require_watchdog_readiness(
                    watchdog_path, graphroot=graphroot, wall=wall,
                    max_age=watchdog_max_age, snapshot=snapshot)
            else:
                heartbeat.read_alive(root, wall=wall, max_age=watchdog_max_age,
                                     target=watchdog_path)
        except GuardExceeded as exc:
            from . import watchdog
            blocked = [{"reason": exc.reason,
                        "detail": "independent watchdog not observing"}]
            watchdog.blocked_evidence(root, "admission", exc.reason,
                                      blocked[0]["detail"])
            raise OrphanLease(report(blocked, [], watchdog_required=True)) from exc
    result = reconcile(root, env, **kwargs)
    # Modes the independent watchdog cannot supervise are unsafe to admit
    # while it is armed: such a lease would be refused by the observer but
    # could still outlive a crashed controller unattended.
    if graphroot is not None:
        from . import watchdog_contract
        for worker, event in latest(events(root)).items():
            if (event.get("state") == "active"
                    and event.get("mode") not in watchdog_contract.SUPPORTED_MODES):
                try:
                    watchdog_contract.require_supported_mode(event.get("mode"))
                except GuardExceeded as exc:
                    blocked = [{"lease": worker, "reason": exc.reason,
                                "detail": "unsupported lease under armed watchdog"}]
                    raise OrphanLease(
                        report(blocked, [], watchdog_required=True)) from exc
    if result["blocked"]:
        raise OrphanLease(result)
    return result
