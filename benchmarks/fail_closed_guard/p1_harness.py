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

from . import (binding, build, disk, heartbeat, lease, natural_exit, proc,
               startup, stop, teardown, watch, watchdog, watchdog_contract)
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


def _late_cid(lease_root, ident, owner, cidfile):
    """Read a valid exact CID only from THIS lease's pinned cidfile.

    Ownership is proven from the append-only lease journal (same active lease,
    owner, mode and pinned path) before the safe file is read. Nothing is
    discovered by container naming or listing, and a journal fault is never
    downgraded into permission to signal or release.
    """
    try:
        current = lease.latest(lease.events(lease_root)).get(str(ident))
    except (GuardExceeded, OSError, ValueError):
        return None, "journal_unavailable"
    if current is None or current.get("state") != "active":
        return None, "lease_inactive"
    if str(current.get("owner")) != str(owner):
        return None, "owner_mismatch"
    if current.get("mode") != "pilot":
        return None, "mode_mismatch"
    if current.get("cidfile") != str(cidfile):
        return None, "cidfile_mismatch"
    journal_cid = current.get("cid")
    try:
        cid = binding.read_cid(cidfile)
    except (GuardExceeded, OSError):
        # A journal CID that was already attested conflicts with a CID that is
        # now absent or unreadable. Never let a caller's prior observation
        # override that conflict, and never treat a symlink or malformed file
        # as a benign absence.
        if journal_cid is not None:
            return None, "cid_mismatch"
        return None, ("absent" if binding.cidfile_absent(cidfile)
                      else "cidfile_unavailable")
    if journal_cid is not None and journal_cid != cid:
        return None, "cid_mismatch"
    return cid, None


def _startup_abort(lease_root, ident, owner, cidfile, exc, *, stopper,
                   snapshot, handle, known_cid=None, launcher_group=None):
    """Fail-closed startup abort after a post-spawn failure.

    A valid exact CID is torn down only after durable ownership is proved.
    A CID read earlier from this lease's pinned cidfile may fill a genuinely
    absent or unreadable file, but journal, lease, owner and CID mismatches
    are terminal: a local observation never overrides a failed ownership
    proof. With no CID, the exact launcher handle may be reaped only through
    the process-group identity captured at spawn; rereading its PID here can
    select a reused process. The pinned cidfile is rechecked after launcher
    handling even when the launcher already exited, because Podman can write
    the CID just before termination. No arbitrary PID is signalled, no lease
    is released, and every outcome is durable evidence.
    """
    reason = exc.reason if isinstance(exc, GuardExceeded) else "startup_failure"
    evidence = {
        "event": "startup_abort", "lease_id": str(ident), "owner": str(owner),
        "cidfile": str(cidfile), "reason": reason, "detail": str(exc)[:200],
        "lease_state": "active_unreleased",
    }
    cid, problem = _late_cid(lease_root, ident, owner, cidfile)
    if known_cid is not None and cid is None and problem == "absent":
        # Only a genuinely absent pinned file may be filled by the exact CID
        # read from that same path earlier. Malformed, symlinked and journal
        # conflicting paths remain terminal.
        cid, problem = known_cid, None
    elif cid is not None and known_cid is not None and cid != known_cid:
        cid, problem = None, "cid_mismatch"

    def remove_exact(target):
        try:
            proof = stopper(target)
            teardown.require_proof(proof, target)
            evidence["teardown"] = proof
            evidence["teardown_result"] = "proven"
        except Exception as stop_exc:
            evidence["teardown_error"] = str(stop_exc)[:200]
            evidence["teardown_result"] = "unproven"

    if cid is not None:
        evidence["cid"] = cid
        remove_exact(cid)
    else:
        evidence["late_cid"] = problem or "absent"
        # Only the exact handle returned by spawn may be reaped. An injected
        # poll seam is never a licence to signal a PID.
        if (handle is not None and not isinstance(handle, bool)
                and callable(getattr(handle, "poll", None))
                and callable(getattr(handle, "wait", None))
                and getattr(handle, "pid", None) is not None):
            try:
                if handle.poll() is not None:
                    # The exact launcher is gone. Its PID may already be
                    # reused, so no process group may be signalled here.
                    evidence["launcher_alive"] = False
                elif launcher_group is None:
                    raise GuardExceeded("launcher_identity_unavailable")
                else:
                    # Re-derive the group from a fresh snapshot and require the
                    # same identity immediately before any signal is sent.
                    fresh = snapshot() if callable(snapshot) else snapshot
                    current_group = build.bind_launcher(
                        int(handle.pid), snapshot=fresh)
                    if (current_group.get("pgid") != launcher_group.get("pgid")
                            or current_group.get("fingerprint")
                            != launcher_group.get("fingerprint")):
                        raise GuardExceeded("launcher_identity_lost")
                    if handle.poll() is not None:
                        evidence["launcher_alive"] = False
                    else:
                        evidence["launcher_group"] = build.stop_group(
                            launcher_group, handle)
            except Exception as stop_exc:
                evidence["launcher_teardown_error"] = str(stop_exc)[:200]
        # A container can appear before or during launcher exit, so the pinned
        # cidfile is rechecked on every no-CID abort path. A prior known CID
        # mismatch is never bypassed by a later read of a different CID.
        late, late_problem = _late_cid(lease_root, ident, owner, cidfile)
        if late is not None and (known_cid is None or late == known_cid):
            evidence["cid"] = late
            remove_exact(late)
        else:
            evidence["late_cid_after_reap"] = (
                "cid_mismatch" if late is not None and known_cid is not None
                else late_problem or "absent")

    # Explicit durable evidence before any caller is told the arm failed; no
    # silent gap when teardown itself is unavailable or unproven.
    try:
        watchdog.blocked_evidence(
            lease_root, ident, reason,
            detail=(evidence.get("teardown_error")
                    or evidence.get("launcher_teardown_error")
                    or evidence.get("detail")))
    except Exception as exc2:
        evidence["watchdog_evidence_error"] = str(exc2)[:200]
    _audit(lease_root, evidence)
    return evidence


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
    if (isinstance(interval, bool) or not isinstance(interval, (int, float))
            or not math.isfinite(interval) or interval <= 0 or interval > 1):
        # Same reviewed sampling bound as the watcher/monitor, before any
        # lock, lease, heartbeat or spawn side effect.
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
        acquired = lease.acquisition_start(lease_root, ident)
        if (not isinstance(acquired, (int, float))
                or not math.isfinite(acquired)):
            raise GuardExceeded("invalid_lease")
        # The independent watchdog stops granting startup grace 120s after
        # durable acquisition. Never wait past that boundary, even when the
        # caller's wall/absolute budget is longer.
        grace_deadline = acquired + watchdog.DEFAULT_STARTUP_BIND_GRACE
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

        stopper = stop_cid or (lambda c: teardown.stop_cid(env, c))
        try:
            spawned = spawn(cidfile, env)
        except Exception as exc:
            failure = GuardExceeded("spawn_failed")
            _audit(lease_root, {"event": "spawn_failed", "lease_id": ident,
                                "owner": str(owner), "cidfile": cidfile,
                                "detail": str(exc)[:200]})
            # A launcher that wrote its pinned cidfile before raising may
            # already own a live container; it must not be abandoned.
            _startup_abort(lease_root, ident, owner, cidfile, failure,
                           stopper=stopper, snapshot=snapshot, handle=None)
            raise failure from exc

        # Exact CID comes only from the cidfile pinned to THIS lease. Podman
        # writes --cidfile asynchronously after spawn; only true absence of a
        # safe cidfile may be retried while the exact launcher is still alive,
        # within the shared finite monotonic/absolute total budget AND the
        # watchdog's reviewed startup grace from durable acquisition. Every
        # wait pass refreshes the controller heartbeat and re-verifies the
        # live independent watchdog, STOP ownership and disk reserve. Any
        # post-spawn failure goes through _startup_abort: a valid late CID is
        # removed by exact CID with fresh absence proof, otherwise only the
        # exact returned launcher group may be reaped, and no lease is ever
        # released without proof.
        tick = clock if clock is not None else time.monotonic
        start = tick()
        poll = (launcher.poll if callable(getattr(launcher, "poll", None))
                else launcher)
        if launcher is None and callable(getattr(spawned, "poll", None)):
            launcher = spawned
            poll = spawned.poll
        # Only the exact handle returned by spawn may ever be reaped; an
        # injected poll seam is never a licence to signal a PID.
        owned_launcher = (
            spawned if callable(getattr(spawned, "poll", None))
            and callable(getattr(spawned, "wait", None)) else None)
        # Bind the launcher's process-group identity now, while the exact
        # handle just returned by spawn is still live. Reading handle.pid in
        # the abort path could resolve a PID that has since been reused.
        launcher_group = None
        if (owned_launcher is not None
                and callable(getattr(owned_launcher, "poll", None))
                and getattr(owned_launcher, "pid", None) is not None):
            try:
                if owned_launcher.poll() is None:
                    launcher_pid = int(owned_launcher.pid)
                    if launcher_pid <= 0:
                        raise GuardExceeded("invalid_launcher")
                    table = snapshot() if callable(snapshot) else snapshot
                    launcher_group = build.bind_launcher(
                        launcher_pid, snapshot=table)
            except Exception as capture_exc:
                _audit(lease_root, {
                    "event": "launcher_identity_unavailable",
                    "lease_id": ident, "owner": str(owner),
                    "detail": str(capture_exc)[:200]})
        sleep_fn = sleep if sleep is not None else time.sleep
        cid = None
        try:
            while True:
                remaining_mono = wall_seconds - (tick() - start)
                remaining_epoch = deadline_utc - time.time()
                remaining = min(remaining_mono, remaining_epoch,
                                grace_deadline - time.time())
                if remaining <= 0:
                    _audit(lease_root, {"event": "bind_unavailable",
                                        "lease_id": ident, "owner": str(owner),
                                        "cidfile": cidfile,
                                        "detail": "deadline"})
                    raise GuardExceeded("binding_unavailable")
                require_owned_stop(stop_path, owner)
                try:
                    emitter.refresh()
                except Exception as exc:
                    raise GuardExceeded("heartbeat_unavailable") from exc
                require_watchdog_ready(checker=watchdog_ready,
                                       path=watchdog_path,
                                       graphroot=watchdog_graphroot,
                                       wall=watchdog_wall,
                                       snapshot=watchdog_snapshot)
                disk.check_reserve(disk_path, reserve, usage=disk_usage)
                try:
                    cid = binding.read_cid(cidfile)
                    break
                except (GuardExceeded, OSError) as exc:
                    launcher_alive = callable(poll) and poll() is None
                    if not launcher_alive or not binding.cidfile_absent(
                            cidfile):
                        _audit(lease_root, {"event": "bind_unavailable",
                                            "lease_id": ident,
                                            "owner": str(owner),
                                            "cidfile": cidfile})
                        raise GuardExceeded("binding_unavailable") from exc
                    sleep_fn(min(interval, remaining))
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
            _startup_abort(lease_root, ident, owner, cidfile, exc,
                           stopper=stopper, snapshot=snapshot,
                           handle=owned_launcher, known_cid=cid,
                           launcher_group=launcher_group)
            reason = exc.reason if isinstance(exc, GuardExceeded) \
                else "measurement_unavailable"
            raise GuardExceeded(reason) from exc

        # The exact CID is now durably attached to the SAME pre-spawn lease.
        try:
            lease.bind_cid(lease_root, ident, cid, owner=owner,
                           cidfile=cidfile, pid=bound.get("pid"),
                           fingerprint=bound.get("fingerprint"))
        except Exception as exc:
            _startup_abort(lease_root, ident, owner, cidfile, exc,
                           stopper=stopper, snapshot=snapshot,
                           handle=owned_launcher, known_cid=cid,
                           launcher_group=launcher_group)
            raise GuardExceeded("lease_journal_unavailable") from exc
        try:
            emitter.bound(cid)
        except Exception as exc:
            failure = GuardExceeded("heartbeat_unavailable")
            _startup_abort(lease_root, ident, owner, cidfile, failure,
                           stopper=stopper, snapshot=snapshot,
                           handle=owned_launcher, known_cid=cid,
                           launcher_group=launcher_group)
            raise failure from exc

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

        # The one monotonic start above covers bind-wait, watcher and
        # natural-exit attestation; launcher/poll were resolved before spawn
        # binding so the abort path and attestation use the same exact handle.
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
