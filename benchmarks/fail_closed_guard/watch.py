"""Prospective bounded userspace watcher over injected snapshots."""
import time

from . import identity, tree
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


def _result(binding, peak, teardown, teardown_error=None):
    result = {"peak_rss": peak, "cid": binding.get("cid"), "teardown": teardown,
              "enforcement": "userspace_observed", "kernel_enforcement": False}
    if teardown_error is not None:
        result["teardown_error"] = teardown_error
    return result


def watch_bound(binding, *, limit, wall_seconds, running, snapshot, measure,
                stop, clock=time.monotonic, sleep=time.sleep, audit=None,
                interval=0.5, rss_fn=None):
    """Sample a bound container tree; fail closed on any unknown state.

    `stop(cid)` must be CID-only with teardown proof. The watcher never
    signals a PID itself. Every exit path, including wall/disk/identity
    failures and tool exceptions, proves teardown of the exact CID before the
    caller may release its lease. Peak and proof travel with a fail-closed
    exception so a killed arm still carries its real measurement.
    """
    if limit <= 0 or wall_seconds <= 0 or interval <= 0:
        raise GuardExceeded("invalid_config")
    start = clock()
    peak = 0
    teardown = None
    stopped = False
    cid = binding.get("cid")

    def collect(exc):
        """Attach evidence to a fail-closed exception before it escapes."""
        exc.peak_rss = peak
        exc.guard_result = _result(binding, peak, teardown,
                                   teardown_error=exc.teardown_error)
        if teardown is not None:
            exc.teardown = teardown
        return exc

    try:
        while running():
            if clock() - start >= wall_seconds:
                raise GuardExceeded("wall_limit")
            table = snapshot()
            try:
                if rss_fn is None:
                    pid = identity.locate(binding["fingerprint"], table)
                    group = tree.members(table, pid, binding["fingerprint"])
                    used = tree.rss_bytes(table, group)
                else:
                    group = []
                    used = rss_fn(table, binding)
            except GuardExceeded as exc:
                # A process that has already exited is a completed arm, not a
                # breach. While it is still live, identity loss is fail-closed.
                if exc.reason == "identity_lost" and not running():
                    break
                raise
            peak = max(peak, used)
            if used > limit:
                event = {"schema": "ivanka.fail-closed-guard.v1",
                         "reason": "observed_rss_limit", "cid": cid,
                         "rss_tree_bytes": used, "members": len(group),
                         "kernel_enforcement": False}
                if audit is not None:
                    audit(event)
                teardown = stop(cid)
                stopped = True
                raise GuardExceeded("observed_rss_limit")
            try:
                if measure() is None:
                    raise GuardExceeded("measurement_unavailable")
            except GuardExceeded:
                raise
            except Exception as exc:
                # An unreadable overlay or vanished path is not a zero-byte
                # disk reading; never continue the arm on that assumption.
                raise GuardExceeded("measurement_unavailable") from exc
            sleep(interval)
    except GuardExceeded as exc:
        if not stopped:
            # Wall, disk, identity and teardown-of-measurement failures all
            # still own the exact container. Remove it before lease release.
            try:
                teardown = stop(cid)
                exc.teardown = teardown
            except Exception as stop_exc:
                exc.teardown_error = str(stop_exc)[:320]
        raise collect(exc)
    except Exception as exc:
        # A harness timeout or killed monitoring tool is not an arm result.
        guarded = GuardExceeded("measurement_unavailable")
        try:
            teardown = stop(cid)
            guarded.teardown = teardown
        except Exception as stop_exc:
            guarded.teardown_error = str(stop_exc)[:320]
        raise collect(guarded) from exc

    # A monitor that merely observes the launcher exit has not torn anything
    # down. Stop and prove the exact bound resource before reporting success.
    try:
        teardown = stop(cid)
    except Exception as exc:
        raise GuardExceeded("teardown_unverified") from exc
    return _result(binding, peak, teardown)
