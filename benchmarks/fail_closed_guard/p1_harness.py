"""Prospective P1 harness integration on the shared fail_closed_guard.

SOURCE-ONLY: this module never starts a container, writes a real STOP sentinel,
takes the PX shared lock, edits a receipt, or touches frozen MiCall / images /
sealed evidence. The caller supplies the spawn callable and the bounded
operation (``running`` / ``measure``); the adapter only gates and observes.

Lifecycle ordering (PR505 + follow-up review): the exclusive lock is taken
first; STOP, prior leases, watchdog readiness and the disk reserve are then
re-checked under that lock; only then are a durable lease and a unique pinned
cidfile recorded. A controller heartbeat is emitted before spawn, the exact
CID is inspected/sampled/re-inspected and bound to the SAME lease, and the
heartbeat is refreshed throughout the watch. A gate failure before lease
acquisition leaves no spurious active pending lease; a crash between spawn
and bind leaves the lease open and admission blocked. Caller deadlines and
disk margins are capped by policy. There is no foreign-name acceptance path.

Evidence honesty: earlier P1 peaks (~38 MB) sampled the Podman launcher process
group and were mislabelled ``whole_container_process_tree``. They are RETAINED
as diagnostic only with ``memory_scope=unverified``; no hard-cap claim is made.
Callers may describe method/version but can never override
``kernel_enforcement=False``, ``enforcement`` or the measured RSS scope.
"""
import fcntl
import json
import math
import os
import secrets
import time
from pathlib import Path

from . import (binding, disk, heartbeat, lease, natural_exit, proc, startup,
               stop, teardown, watch, watchdog_contract)
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


def _bounded_reserve(reserve_bytes):
    """A caller may raise the disk margin but never shrink the policy floor."""
    if (isinstance(reserve_bytes, bool)
            or not isinstance(reserve_bytes, (int, float))
            or not math.isfinite(reserve_bytes) or reserve_bytes <= 0):
        raise GuardExceeded("invalid_config")
    return max(int(reserve_bytes), DEFAULT_RESERVE_BYTES)


def _bounded_deadline(caller_deadline, durable_cap):
    """A caller may only shorten the durable absolute deadline."""
    if caller_deadline is None:
        return durable_cap
    if (isinstance(caller_deadline, bool)
            or not isinstance(caller_deadline, (int, float))
            or not math.isfinite(caller_deadline)):
        raise GuardExceeded("invalid_config")
    return min(float(caller_deadline), durable_cap)


def run_prospective(*, owner, lease_root, stop_path, disk_path, spawn,
                    env=None, lock_path=None, lock=None,
                    watchdog_ready=None, watchdog_path=None,
                    watchdog_graphroot=None, watchdog_snapshot=None,
                    watchdog_wall=None,
                    disk_reserve_bytes=DEFAULT_RESERVE_BYTES, disk_usage=None,
                    limit=4_000_000_000, wall_seconds=2400, deadline_utc=None,
                    running=None, measure=None, snapshot=None, clock=None,
                    sleep=None, audit=None, attestation=None,
                    bind_container=None, stop_cid=None, launcher=None,
                    interval=0.5):
    """Run a caller-supplied spawn under the durable pre-spawn guard.

    Ordering (review): acquire the exclusive lock FIRST, then re-check STOP,
    lease clearance, watchdog readiness and disk reserve; only then acquire a
    durable lease and unique cidfile, emit a controller heartbeat before
    spawn, and bind the exact inspected CID to that same lease. A failure
    before the lease exists leaves no spurious active pending lease.
    """
    if not owner or running is None or measure is None:
        raise GuardExceeded("invalid_config")
    if launcher is not None and not callable(
            getattr(launcher, "poll", None)) and not callable(launcher):
        # Reject an unusable attestation seam before any lock, lease or spawn.
        raise GuardExceeded("invalid_config")
    env = dict(env or {})
    reserve = _bounded_reserve(disk_reserve_bytes)

    # Gate 1: STOP must already be armed for this caller.
    require_owned_stop(stop_path, owner)
    ctx = lock if lock is not None else (
        ExclusiveLock(lock_path) if lock_path is not None else None)
    if ctx is None:
        raise GuardExceeded("lock_unavailable")

    with ctx:
        # Gate 2: re-check STOP, prior leases, watchdog readiness and the
        # independent disk reserve while holding the lock. No lease exists
        # yet, so a gate failure cannot leave an active pending lease.
        require_owned_stop(stop_path, owner)
        lease.require_clear(lease_root, env)
        require_watchdog_ready(checker=watchdog_ready, path=watchdog_path,
                               graphroot=watchdog_graphroot,
                               wall=watchdog_wall, snapshot=watchdog_snapshot)
        disk.check_reserve(disk_path, reserve, usage=disk_usage)

        # Gate 3: durable ownership and a unique pinned cidfile BEFORE spawn.
        token = secrets.token_hex(12)
        ident = "p1-%s-%s" % (str(owner), token)
        cidfile = pin_cidfile(lease_root, ident)
        lease.acquire(lease_root, ident, "pilot", owner=owner, cidfile=cidfile)
        # One absolute epoch deadline covers pre-spawn gates, bind and
        # sampling. A caller may shorten it but never extend the durable cap.
        durable_cap = watchdog_contract.durable_deadline(
            lease_root, ident, wall_seconds)
        deadline_utc = _bounded_deadline(deadline_utc, durable_cap)
        if time.time() >= deadline_utc:
            raise GuardExceeded("wall_limit")

        # The independent watchdog must observe a live controller from before
        # spawn through every sample; otherwise the arm is killed at first
        # observation as an orphan.
        emitter = heartbeat.Emitter(lease_root, ident)
        try:
            emitter.before_spawn()
        except Exception as exc:
            raise GuardExceeded("heartbeat_unavailable") from exc

        try:
            spawned = spawn(cidfile, env)
        except Exception as exc:
            _audit(lease_root, {"event": "spawn_failed", "lease_id": ident,
                                "owner": str(owner), "cidfile": cidfile,
                                "detail": str(exc)[:200]})
            raise GuardExceeded("spawn_failed") from exc

        # Exact CID comes only from the cidfile pinned to THIS lease. Bind it
        # after inspecting, snapshotting and re-inspecting the exact CID; a
        # changed init PID is terminal identity_lost with exact-CID teardown.
        try:
            cid = binding.read_cid(cidfile)
        except GuardExceeded as exc:
            _audit(lease_root, {"event": "bind_unavailable", "lease_id": ident,
                                "owner": str(owner), "cidfile": cidfile})
            raise exc
        stopper = stop_cid or (lambda c: teardown.stop_cid(env, c))
        try:
            pid_before = binding.inspect_pid(cid, env)
            table = snapshot() if callable(snapshot) else (
                snapshot if snapshot is not None else proc.snapshot())
            if binding.inspect_pid(cid, env) != pid_before:
                raise GuardExceeded("identity_lost")
            binder = bind_container or binding.bind_container
            bound = binder(cid, env, snapshot=table)
            if (not isinstance(bound, dict) or bound.get("cid") != cid
                    or bound.get("pid") != pid_before):
                raise GuardExceeded("identity_lost")
            record = table.get(pid_before) if isinstance(table, dict) else None
            if record is None:
                raise GuardExceeded("identity_lost")
            expected = list(startup.stable_fingerprint(record))
            if list(bound.get("fingerprint") or []) != expected:
                raise GuardExceeded("identity_lost")
        except Exception as exc:
            reason = exc.reason if isinstance(exc, GuardExceeded) \
                else "measurement_unavailable"
            try:
                stopper(cid)
            except Exception:
                pass
            _audit(lease_root, {"event": "bind_failed", "lease_id": ident,
                                "owner": str(owner), "cid": cid,
                                "reason": reason})
            raise GuardExceeded(reason) from exc

        # The exact CID is now durably attached to the SAME pre-spawn lease.
        lease.bind_cid(lease_root, ident, cid, owner=owner, cidfile=cidfile,
                       pid=bound.get("pid"), fingerprint=bound.get("fingerprint"))
        try:
            emitter.bound(cid)
        except Exception as exc:
            try:
                stopper(cid)
            except Exception:
                pass
            raise GuardExceeded("heartbeat_unavailable") from exc

        def refresh_ready():
            # The controller keeps its own heartbeat fresh and re-checks that
            # the independent observer is still ready on every sample. A
            # watchdog that became stale/failed mid-arm must fail this arm
            # closed rather than supervise it unobserved.
            emitted = emitter.refresh()
            require_watchdog_ready(checker=watchdog_ready, path=watchdog_path,
                                   graphroot=watchdog_graphroot,
                                   wall=watchdog_wall,
                                   snapshot=watchdog_snapshot)
            return emitted

        # One monotonic start covers the watcher and natural-exit attestation,
        # so a lagging launcher cannot grant the arm a second wall budget.
        tick = clock if clock is not None else time.monotonic
        start = tick()
        poll = (launcher.poll if callable(getattr(launcher, "poll", None))
                else launcher)
        if launcher is None and callable(getattr(spawned, "poll", None)):
            # A spawn that returns its launcher handle lets the adapter attest
            # the real integer result instead of relying on a lagging poll.
            launcher = spawned
            poll = spawned.poll
        kwargs = {}
        for key, value in (("clock", clock), ("sleep", sleep), ("audit", audit)):
            if value is not None:
                kwargs[key] = value
        kwargs["start"] = start
        if launcher is not None:
            if not callable(poll):
                raise GuardExceeded("natural_exit_unverified")
            kwargs["attest_exit"] = (
                lambda: natural_exit.wait_and_attest(
                    cid, env, poll, start=start, wall_seconds=wall_seconds,
                    interval=interval, clock=tick,
                    sleep=(sleep if sleep is not None else time.sleep),
                    deadline_utc=deadline_utc))

        proof = None
        outcome = None
        try:
            result = watch.watch_bound(
                bound, limit=limit, wall_seconds=wall_seconds, running=running,
                snapshot=(lambda: snapshot() if callable(snapshot)
                          else (snapshot if snapshot is not None
                                else proc.snapshot())),
                measure=measure, stop=stopper,
                disk_path=disk_path, disk_reserve_bytes=reserve,
                disk_usage=disk_usage, strict_proof=True,
                deadline_utc=deadline_utc, heartbeat=refresh_ready,
                interval=interval, attestation=_attestation(attestation),
                **kwargs)
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
