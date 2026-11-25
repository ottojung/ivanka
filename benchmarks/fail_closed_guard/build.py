"""Build-mode identity: no container CID, so bind the launcher tree."""
import os
import signal

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
    pid = identity.locate(binding["fingerprint"], table)
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
