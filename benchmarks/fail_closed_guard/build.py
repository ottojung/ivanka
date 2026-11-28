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


def stop_group_by_id(pgid, *, snapshot=None, sleep=None, clock=None,
                     timeout=5, verify=None, absent=None):
    """Signal only an exactly verified live group; prove absence conservatively.

    ``verify(pgid, table)`` must confirm the bound immutable identity before
    every signal and ``absent(pgid, table)`` must prove the exact group is gone
    before a proof is claimed. With either callback missing the call refuses,
    so a reused PGID is never signalled or reported as reaped. A bound helper
    that already exited on its own is a completed teardown, not identity loss:
    proven absence resolves without sending any signal.
    """
    pgid = int(pgid)
    if pgid <= 0 or verify is None or absent is None:
        raise TeardownError("identity_unverified")
    now = clock if clock is not None else time.monotonic
    nap = sleep if sleep is not None else time.sleep
    take = snapshot if snapshot is not None else proc.snapshot
    deadline = now() + timeout
    table = take()
    if not verify(pgid, table):
        if absent(pgid, table):
            # A fast COPY-only helper can finish before its stop callback.
            # Proof that neither the bound identity nor its PGID remains is a
            # verified natural exit: no signal is sent and no live group is
            # claimed as reaped. An unattestable or live group is still refused.
            return {"process_group": pgid, "stopped": True,
                    "method": "verified_exact_group",
                    "pre_exited": True, "kernel_enforcement": False}
        raise TeardownError("identity_lost_before_signal")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    while True:
        table = take()
        if absent(pgid, table) and not verify(pgid, table):
            return {"process_group": pgid, "stopped": True,
                    "method": "verified_exact_group", "kernel_enforcement": False}
        if now() >= deadline:
            raise TeardownError("build_group_survived")
        nap(min(0.1, max(0.0, deadline - now())))
