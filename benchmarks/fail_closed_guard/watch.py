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


def watch_bound(binding, *, limit, wall_seconds, running, snapshot, measure,
                stop, clock=time.monotonic, sleep=time.sleep, audit=None,
                interval=0.5, rss_fn=None):
    """Sample a bound container tree; fail closed on any unknown state.

    `stop(cid)` must be CID-only with teardown proof. The watcher never
    signals a PID itself. Disk admission errors propagate as fail-closed.
    """
    if limit <= 0 or wall_seconds <= 0 or interval <= 0:
        raise GuardExceeded("invalid_config")
    start = clock()
    peak = 0
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
                     "reason": "observed_rss_limit", "cid": binding.get("cid"),
                     "rss_tree_bytes": used, "members": len(group),
                     "kernel_enforcement": False}
            if audit is not None:
                audit(event)
            stop(binding.get("cid"))
            raise GuardExceeded("observed_rss_limit")
        if measure() is None:
            raise GuardExceeded("measurement_unavailable")
        sleep(interval)
    # A monitor that merely observes the launcher exit has not torn anything
    # down. Stop and prove the exact bound resource before reporting success.
    try:
        teardown = stop(binding.get("cid"))
    except Exception as exc:
        raise GuardExceeded("teardown_unverified") from exc
    return {"peak_rss": peak, "cid": binding.get("cid"), "teardown": teardown,
            "enforcement": "userspace_observed", "kernel_enforcement": False}
