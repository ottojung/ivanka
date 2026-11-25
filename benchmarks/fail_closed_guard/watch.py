"""Prospective bounded userspace watcher over injected snapshots."""
import time

from . import disk, identity, startup, tree
from .errors import GuardExceeded


def audit_event(path, event):
    import json
    import os
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def _result(binding, peak, teardown, teardown_error=None, attestation=None,
            identity_observation=None, disk_observation=None):
    result = {"peak_rss": peak, "cid": binding.get("cid"), "teardown": teardown,
               "enforcement": "userspace_observed", "kernel_enforcement": False}
    # Only a caller that actually ran the bound whole-container sampler may
    # supply method/version/scope. Carry them on every exit so a killed arm
    # keeps the same real sampling evidence as a finished one.
    if attestation:
        result.update(attestation)
    if teardown_error is not None:
        result["teardown_error"] = teardown_error
    if identity_observation is not None:
        result["identity_observation"] = identity_observation
    if disk_observation is not None:
        result["disk_observation"] = disk_observation
    return result


def _valid_proof(proof, cid, strict):
    """Validate teardown evidence before any exit is reported as success.

    Build-mode guards have no container CID (``cid`` is None) and prove an
    exact launcher process group instead; pilots must carry the matching CID.
    """
    if not isinstance(proof, dict):
        return False
    if cid is not None and proof.get("cid") != cid:
        return False
    if proof.get("container_removed") is not True:
        # Build-mode guards have no container; they prove an exact process
        # group was stopped instead.
        if not (cid is None and proof.get("stopped") is True
                and proof.get("process_group") is not None):
            return False
    if proof.get("fresh_absence_check") is False:
        return False
    if strict and proof.get("fresh_absence_check") is not True:
        return False
    return True


def watch_bound(binding, *, limit, wall_seconds, running, snapshot, measure,
                stop, clock=time.monotonic, sleep=time.sleep, audit=None,
                interval=0.5, rss_fn=None, attestation=None, start=None,
                disk_path=None, disk_reserve_bytes=None, disk_usage=None,
                strict_proof=False):
    """Sample a bound container tree; fail closed on any unknown state.

    `stop(cid)` must be CID-only with teardown proof. The watcher never
    signals a PID itself. Every exit path, including wall/disk/identity
    failures and tool exceptions, proves teardown of the exact CID before the
    caller may release its lease. Peak and proof travel with a fail-closed
    exception so a killed arm still carries its real measurement.

    `disk_reserve_bytes` wires the independent reserve check into the guard
    loop (fail closed on shortfall or unreadable disk state). `strict_proof`
    requires an explicit fresh absence check on teardown; the P1 adapter
    enables it, while legacy injected stop doubles keep their older shape.
    """
    if limit <= 0 or wall_seconds <= 0 or interval <= 0:
        raise GuardExceeded("invalid_config")
    if disk_reserve_bytes is not None and disk_path is None:
        raise GuardExceeded("invalid_config")
    start = clock() if start is None else start
    peak = None
    teardown = None
    stopped = False
    stop_attempted = False
    last_identity = None
    disk_observation = None
    if disk_reserve_bytes is not None:
        disk_observation = {"path": str(disk_path),
                            "reserve_bytes": int(disk_reserve_bytes)}
    cid = binding.get("cid")

    def collect(exc):
        """Attach evidence to a fail-closed exception before it escapes."""
        exc.peak_rss = peak
        exc.identity_observation = last_identity
        exc.guard_result = _result(
            binding, peak, teardown, teardown_error=exc.teardown_error,
            attestation=attestation, identity_observation=last_identity,
            disk_observation=disk_observation)
        if teardown is not None:
            exc.teardown = teardown
        return exc

    def stop_once():
        nonlocal teardown, stopped, stop_attempted
        if stopped:
            return teardown
        stop_attempted = True
        try:
            proof = stop(cid)
        except Exception as exc:
            raise GuardExceeded("teardown_unverified",
                                teardown_error=str(exc)[:320]) from exc
        if not _valid_proof(proof, cid, strict_proof):
            raise GuardExceeded("teardown_unverified", teardown=proof,
                                teardown_error="invalid_proof_shape")
        teardown = proof
        stopped = True
        return proof

    def fail_close(exc):
        """Ensure exact teardown happened (or record why it could not)."""
        if not stopped and not stop_attempted:
            try:
                exc.teardown = stop_once()
            except GuardExceeded as stop_exc:
                exc.teardown = stop_exc.teardown
                exc.teardown_error = stop_exc.teardown_error
        return collect(exc)

    try:
        while running():
            if clock() - start >= wall_seconds:
                raise GuardExceeded("wall_limit")
            if disk_reserve_bytes is not None:
                disk_observation["free_bytes"] = disk.check_reserve(
                    disk_path, disk_reserve_bytes, usage=disk_usage)
            table = snapshot()
            if binding.get("stable"):
                last_identity = startup.observation(binding, table)
            try:
                if rss_fn is None:
                    if binding.get("stable"):
                        # A normal exec changes cmdline but not starttime/ns.
                        pid = startup.locate(binding, table,
                                             bound_pid=binding.get("pid"))
                    else:
                        pid = identity.locate(binding["fingerprint"], table,
                                              bound_pid=binding.get("pid"))
                    group = tree.members(table, pid, binding["fingerprint"])
                    used = tree.rss_bytes(table, group)
                else:
                    group = []
                    used = rss_fn(table, binding)
            except GuardExceeded as exc:
                if exc.reason == "identity_lost" and not running():
                    break
                raise
            peak = used if peak is None else max(peak, used)
            if used > limit:
                event = {"schema": "ivanka.fail-closed-guard.v1",
                         "reason": "observed_rss_limit", "cid": cid,
                         "rss_tree_bytes": used, "members": len(group),
                         "kernel_enforcement": False}
                if audit is not None:
                    audit(event)
                stop_once()
                raise GuardExceeded("observed_rss_limit")
            try:
                if measure() is None:
                    raise GuardExceeded("measurement_unavailable")
            except GuardExceeded:
                raise
            except Exception as exc:
                raise GuardExceeded("measurement_unavailable") from exc
            sleep(interval)
    except GuardExceeded as exc:
        raise fail_close(exc)
    except Exception as exc:
        raise fail_close(GuardExceeded("measurement_unavailable")) from exc

    # A monitor that merely observes the launcher exit has not torn anything
    # down. Stop and prove the exact bound resource before reporting success.
    try:
        stop_once()
    except GuardExceeded as exc:
        raise collect(exc)
    return _result(binding, peak, teardown, attestation=attestation,
                   identity_observation=last_identity,
                   disk_observation=disk_observation)
