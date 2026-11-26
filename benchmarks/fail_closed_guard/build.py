"""Build-mode identity: no container CID, so bind the launcher tree."""
import os
import signal
import time

from . import identity, proc, tree
from .errors import GuardExceeded, TeardownError


def bind_launcher(pid, snapshot=None):
    table = snapshot if snapshot is not None else proc.snapshot()
    record = table.get(pid)
    if record is None:
        raise GuardExceeded("binding_unavailable")
    return {"pid": pid, "pgid": pid,
            "fingerprint": identity.bind(record)}


def rss(table, binding):
    """Builds share the host PID namespace: use identity + PPID descendants."""
    pid = identity.locate(binding["fingerprint"], table,
                          bound_pid=binding.get("pid"))
    return tree.rss_bytes(table, tree.descendants(table, pid))


def stop_group(binding, proc_handle, timeout=5):
    """Signal the exact launcher process group, never a bare PID."""
    pgid = binding["pgid"]
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc_handle.wait(timeout=timeout)
    except Exception as exc:
        raise TeardownError("build_group_survived") from exc
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return {"process_group": pgid, "stopped": True}
    raise TeardownError("build_group_survived")


def stop_group_by_id(pgid, *, snapshot=None, sleep=None, clock=None, timeout=5):
    """Signal and prove absence of one exact process group, without a handle.

    The watchdog has no ``Popen`` object for a group a crashed controller
    created, so it confirms absence from ``/proc`` and a final ``killpg(pgid, 0)``
    probe. An invalid pgid is refused before any signal.
    """
    pgid = int(pgid)
    if pgid <= 0:
        raise TeardownError("invalid_group")
    now = clock if clock is not None else time.monotonic
    nap = sleep if sleep is not None else time.sleep
    take = snapshot if snapshot is not None else proc.snapshot
    deadline = now() + timeout
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    while True:
        live = [pid for pid, record in take().items()
                if record.get("pgid") == pgid]
        if not live:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return {"process_group": pgid, "stopped": True,
                        "method": "exact_pgid", "kernel_enforcement": False}
        if now() >= deadline:
            raise TeardownError("build_group_survived")
        nap(min(0.1, max(0.0, deadline - now())))
