"""Prospective P1 harness integration on the shared fail_closed_guard.

SOURCE-ONLY: this module never starts a container, writes a real STOP sentinel,
takes the PX shared lock, edits a receipt, or touches frozen MiCall / images /
sealed evidence. The caller supplies the spawn callable and the bounded
operation (``running`` / ``measure``); the adapter only gates and observes.

Lifecycle ordering (PR505 review): a durable lease and a unique pinned cidfile
are recorded BEFORE spawn; an owner-bound STOP, an exclusive lock, watchdog
readiness and the disk reserve are all verified BEFORE spawn; only then does
the caller spawn, and the exact CID read from that pinned cidfile is bound to
the SAME lease. There is no foreign container-name acceptance path. A crash
between spawn and bind leaves the lease open and admission blocked.

Evidence honesty: earlier P1 peaks (~38 MB) sampled the Podman launcher process
group and were mislabelled ``whole_container_process_tree``. They are RETAINED
as diagnostic only with ``memory_scope=unverified``; no hard-cap claim is made.
Callers may describe method/version but can never override
``kernel_enforcement=False``, ``enforcement`` or the measured RSS scope.
"""
import fcntl
import json
import os
import secrets
import time
from pathlib import Path

from . import binding, disk, lease, proc, stop, teardown, watch, watchdog_contract
from .errors import GuardExceeded

DEFAULT_RESERVE_BYTES = 32 * 1024 ** 3  # independent project filesystem reserve
RSS_SCOPE = "whole_container_process_tree"
P1_ATTESTATION = {
    "rss_sample_scope": RSS_SCOPE,
    "method": "exact_cid_to_init_pid_starttime_pidns_bound_tree_sampled_rss",
    "version": "ivanka.p1.shared-guard.v2",
    "kernel_enforcement": False,
}
# Only descriptive fields may be supplied by a caller.
CALLER_ATTESTATION_KEYS = ("method", "version")


class ExclusiveLock:
    """Real advisory flock; fail closed when another worker already holds it."""

    def __init__(self, path):
        self.path = Path(path)
        self.fd = None

    def __enter__(self):
        if self.path.is_symlink():
            raise GuardExceeded("lock_unavailable")
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._close()
            raise GuardExceeded("lock_unavailable") from exc
        return self

    def _close(self):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None

    def __exit__(self, *_exc):
        self._close()
        return False


def require_owned_stop(path, owner):
    """STOP must exist and be bound to this exact owner before any spawn."""
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise GuardExceeded("stop_absent")
    if target.read_text().strip() != str(owner):
        raise GuardExceeded("stop_owner_unauthorized")
    return str(target)


def require_watchdog_ready(*, checker=None, path=None, graphroot=None,
                           wall=None, snapshot=None):
    """Require an explicit, currently-ready crash-independent watchdog.

    A readiness checker is injected by the operator/watchdog owner; a readiness
    file is a fallback contract. Absence of either fails closed -- a missing
    watchdog is never treated as a deployed one. When a genuine watchdog
    record is read from a path and its store namespace is known, the shared
    contract also binds freshness, namespace and a live kernel identity;
    injected checkers keep their explicit readiness declaration.
    """
    if path is not None and graphroot is not None and checker is None:
        return watchdog_contract.require_watchdog_readiness(
            path, graphroot=graphroot, wall=wall, snapshot=snapshot)
    if checker is not None:
        try:
            record = checker()
        except Exception as exc:
            raise GuardExceeded("watchdog_unavailable") from exc
        source = "checker"
    elif path is not None:
        target = Path(path)
        if target.is_symlink() or not target.is_file():
            raise GuardExceeded("watchdog_unavailable")
        try:
            record = json.loads(target.read_text())
        except (OSError, ValueError) as exc:
            raise GuardExceeded("watchdog_unavailable") from exc
        source = str(path)
    else:
        raise GuardExceeded("watchdog_unavailable")

    # Identity/namespace readiness is mandatory: a merely "alive" watchdog
    # is not a bound watchdog and cannot cover the crash window.
    if not isinstance(record, dict) or record.get("ready") is not True \
            or record.get("identity_bound") is not True:
        raise GuardExceeded("watchdog_unbound")
    if not isinstance(record.get("pid_ns"), int) or record["pid_ns"] <= 0 \
            or not isinstance(record.get("starttime"), int) \
            or record["starttime"] <= 0:
        raise GuardExceeded("watchdog_unbound")
    result = {"source": source, "ready": True, "identity_bound": True,
              "pid_ns": record["pid_ns"], "starttime": record["starttime"]}
    if record.get("schema"):
        result["schema"] = record["schema"]
    if record.get("cid") is not None:
        if not isinstance(record["cid"], str) or not binding.CID.fullmatch(
                record["cid"]):
            raise GuardExceeded("watchdog_unbound")
        result["cid"] = record["cid"]
    return result


def pin_cidfile(root, ident):
    """Reserve a unique project-owned cidfile path before spawn.

    The cidfile itself must not exist yet (Podman creates it). An exclusive
    O_EXCL marker records the lease/owner/token so a later reconciliation can
    attribute a container that appeared before the CID was bound.
    """
    base = Path(root) / "cidfiles"
    if base.is_symlink():
        raise GuardExceeded("cidfile_unavailable")
    base.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    marker = base / (token + ".pinned")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"lease": str(ident), "at_utc": time.time()}, stream,
                  sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    cidfile = base / (token + ".cid")
    if cidfile.exists() or cidfile.is_symlink():
        raise GuardExceeded("cidfile_collision")
    return str(cidfile)


def _attestation(caller):
    """Build attestation; safety facts can never be caller-controlled."""
    supplied = dict(P1_ATTESTATION)
    if caller is not None:
        if not isinstance(caller, dict):
            raise GuardExceeded("invalid_attestation")
        for key in CALLER_ATTESTATION_KEYS:
            if key in caller:
                supplied[key] = str(caller[key])[:200]
    supplied["rss_sample_scope"] = RSS_SCOPE
    supplied["kernel_enforcement"] = False
    return supplied


def _audit(root, event):
    record = dict(event)
    record["schema"] = lease.SCHEMA
    record["at_utc"] = time.time()
    lease.append(root, record)
    return record


def run_prospective(*, owner, lease_root, stop_path, disk_path, spawn,
                    env=None, lock_path=None, lock=None,
                    watchdog_ready=None, watchdog_path=None,
                    watchdog_graphroot=None, watchdog_snapshot=None,
                    watchdog_wall=None,
                    disk_reserve_bytes=DEFAULT_RESERVE_BYTES, disk_usage=None,
                    limit=4_000_000_000, wall_seconds=2400, deadline_utc=None,
                    running=None, measure=None, snapshot=None, clock=None,
                    sleep=None, audit=None, attestation=None,
                    bind_container=None, stop_cid=None):
    """Run a caller-supplied spawn under the durable pre-spawn guard.

    All pre-spawn gates are checked before ``spawn(cidfile, env)`` is called.
    A failure before an exact-CID teardown proof leaves the lease OPEN and the
    owner-bound STOP in place, so a later controller still fails closed.
    """
    if not owner or running is None or measure is None:
        raise GuardExceeded("invalid_config")
    # One absolute epoch deadline covers pre-spawn gates, bind and sampling;
    # a restarted harness cannot reset an injected monotonic clock to gain time.
    env = dict(env or {})

    # Gate 1: STOP must already be armed for this caller before any lease or
    # spawn. A foreign STOP is refused outright.
    require_owned_stop(stop_path, owner)
    lease.require_clear(lease_root, env)

    # Gate 2: durable ownership and a unique pinned cidfile BEFORE spawn.
    token = secrets.token_hex(12)
    ident = "p1-%s-%s" % (str(owner), token)
    cidfile = pin_cidfile(lease_root, ident)
    lease.acquire(lease_root, ident, "pilot", owner=owner, cidfile=cidfile)
    if deadline_utc is None:
        # Derive the deadline from the durable lease start, not from a fresh
        # clock reading, so a harness restart cannot grant itself more time.
        deadline_utc = watchdog_contract.durable_deadline(
            lease_root, ident, wall_seconds)

    ctx = lock if lock is not None else (
        ExclusiveLock(lock_path) if lock_path is not None else None)
    if ctx is None:
        raise GuardExceeded("lock_unavailable")

    with ctx:
        # Gate 3: watchdog identity/namespace readiness, absolute deadline
        # and independent disk reserve BEFORE spawn.
        if time.time() >= deadline_utc:
            raise GuardExceeded("wall_limit")
        require_watchdog_ready(checker=watchdog_ready, path=watchdog_path,
                               graphroot=watchdog_graphroot,
                               wall=watchdog_wall, snapshot=watchdog_snapshot)
        disk.check_reserve(disk_path, disk_reserve_bytes, usage=disk_usage)

        try:
            spawn(cidfile, env)
        except Exception as exc:
            # Crash after spawn may have created the container; the pinned
            # cidfile and active lease are the only durable evidence we have.
            _audit(lease_root, {"event": "spawn_failed", "lease_id": ident,
                                "owner": str(owner), "cidfile": cidfile,
                                "detail": str(exc)[:200]})
            raise GuardExceeded("spawn_failed") from exc

        # Exact CID comes only from the cidfile pinned to THIS lease. No
        # container name or caller-supplied CID can enter this path.
        try:
            cid = binding.read_cid(cidfile)
        except GuardExceeded as exc:
            _audit(lease_root, {"event": "bind_unavailable", "lease_id": ident,
                                "owner": str(owner), "cidfile": cidfile})
            raise exc
        if not binding.CID.fullmatch(cid):
            raise GuardExceeded("binding_unavailable")

        table = snapshot() if callable(snapshot) else (
            snapshot if snapshot is not None else proc.snapshot())
        binder = bind_container or binding.bind_container
        bound = binder(cid, env, snapshot=table)
        if not isinstance(bound, dict) or bound.get("cid") != cid:
            raise GuardExceeded("identity_lost")
        # The exact CID is now durably attached to the SAME pre-spawn lease.
        lease.bind_cid(lease_root, ident, cid, owner=owner, cidfile=cidfile,
                       pid=bound.get("pid"), fingerprint=bound.get("fingerprint"))

        kwargs = {}
        for key, value in (("clock", clock), ("sleep", sleep), ("audit", audit),
                           ("start", None)):
            if value is not None:
                kwargs[key] = value
        stopper = stop_cid or (lambda c: teardown.stop_cid(env, c))

        proof = None
        outcome = None
        try:
            result = watch.watch_bound(
                bound, limit=limit, wall_seconds=wall_seconds, running=running,
                snapshot=(lambda: snapshot() if callable(snapshot)
                          else (snapshot if snapshot is not None
                                else proc.snapshot())),
                measure=measure, stop=stopper,
                disk_path=disk_path, disk_reserve_bytes=disk_reserve_bytes,
                disk_usage=disk_usage, strict_proof=True,
                deadline_utc=deadline_utc,
                attestation=_attestation(attestation), **kwargs)
            proof = result.get("teardown")
            outcome = {"status": "completed", "result": result}
        except GuardExceeded as exc:
            proof = exc.teardown
            outcome = {"status": "fail_closed", "reason": exc.reason,
                       "result": exc.guard_result,
                       "teardown_error": exc.teardown_error}
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable",
                                teardown_error=str(exc)[:320]) from exc

        if proof is None:
            _audit(lease_root, {"event": "teardown_unverified",
                                "lease_id": ident, "owner": str(owner),
                                "cid": cid})
            raise GuardExceeded("teardown_unverified")

        # Only the owner of the open lease may retire its owned STOP, and only
        # after an exact-CID fresh-absence proof. Retirement closes the lease.
        stop.retire_stop(stop_path, proof, owner=owner, lease_root=lease_root,
                         cid=cid)
        outcome["stop_retired_by"] = str(owner)
        outcome["lease"] = ident
        outcome["deadline_utc"] = deadline_utc
        if outcome["status"] == "fail_closed":
            raise GuardExceeded(outcome["reason"], guard_result=outcome["result"],
                                teardown=proof,
                                teardown_error=outcome.get("teardown_error"))
        return outcome


__all__ = ["run_prospective", "require_owned_stop", "require_watchdog_ready",
           "pin_cidfile", "ExclusiveLock", "DEFAULT_RESERVE_BYTES",
           "RSS_SCOPE", "P1_ATTESTATION", "GuardExceeded"]
