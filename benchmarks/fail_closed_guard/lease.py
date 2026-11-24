"""Durable worker lease journal and read-only startup orphan reconciliation.

An advisory lock only protects a live launcher. If the launcher dies after it
spawns a container but before teardown is proven, the lock is released while
the container is still alive. This journal makes ownership durable: a lease is
appended before spawn and closed only after teardown proof. Startup
reconciliation never signals or removes a container; it refuses admission while
any prior owned resource is alive, leaving teardown with its owner.
"""
import json
import os
import time
from pathlib import Path

from . import binding, proc
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


def acquire(root, ident, mode, *, cidfile=None):
    """Durably record ownership before any process or container is spawned."""
    if mode not in ("pilot", "build") or (mode == "pilot" and cidfile is None):
        raise GuardExceeded("invalid_lease")
    event = {"schema": SCHEMA, "lease": str(ident), "state": "active",
             "mode": mode, "cid": None,
             "cidfile": str(cidfile) if cidfile is not None else None,
             "pid": None, "fingerprint": None, "at_utc": time.time()}
    append(root, event)
    return event


def bind(root, ident, pid, fingerprint=None):
    """Attach build-process identity after spawn; before spawn it is unknown."""
    event = {"schema": SCHEMA, "lease": str(ident), "state": "active",
             "mode": "build", "cid": None, "cidfile": None, "pid": int(pid),
             "fingerprint": list(fingerprint) if fingerprint else None,
             "at_utc": time.time()}
    append(root, event)
    return event


def bind_cid(root, ident, cid, *, cidfile=None, pid=None, fingerprint=None):
    """Durably record the exact pilot CID at the moment it is bound.

    The cidfile is transient (--rm deletes it on natural completion), but the
    journal is append-only evidence of ownership. Reconciliation and cleanup
    therefore use this CID and never need the file again.
    """
    if not isinstance(cid, str) or not binding.CID.fullmatch(cid):
        raise GuardExceeded("invalid_lease")
    event = {"schema": SCHEMA, "lease": str(ident), "state": "active",
             "mode": "pilot", "cid": cid,
             "cidfile": str(cidfile) if cidfile is not None else None,
             "pid": int(pid) if pid is not None else None,
             "fingerprint": list(fingerprint) if fingerprint else None,
             "at_utc": time.time()}
    append(root, event)
    return event


def release(root, ident, *, cid=None, proof=None):
    """Close a lease only after verified teardown (or a proven-absent startup)."""
    event = {"schema": SCHEMA, "lease": str(ident), "state": "released",
             "cid": cid, "proof": proof, "at_utc": time.time()}
    append(root, event)
    return event


def latest(table):
    """Last event per lease wins; the journal remains append-only evidence."""
    return {event["lease"]: event for event in table if "lease" in event}


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
    silently mutates ownership state.
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
                               "reason": "proven_absent"})
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
                    closed.append({"lease": lease_id, "reason": "proven_absent"})
            elif event.get("pid") is not None:
                record = table.get(event["pid"])
                if record is None:
                    closed.append({"lease": lease_id, "reason": "proven_absent"})
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
                          "state": "reconciled", "reason": item["reason"],
                          "at_utc": time.time()})
    return report(blocked, closed)


def require_clear(root, env, **kwargs):
    """Fail closed before admission if any prior owned resource is alive."""
    result = reconcile(root, env, **kwargs)
    if result["blocked"]:
        raise OrphanLease(result)
    return result
