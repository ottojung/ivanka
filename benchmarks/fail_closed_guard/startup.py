"""Identity-safe startup binding for the exact issued container CID.

Why this exists
---------------
The kernel starttime (``/proc/<pid>/stat`` field 22) and the PID-namespace
inode (``/proc/<pid>/ns/pid``) are assigned when the task is created. They are
immutable across ``execve()``. A normal wrapper that execs the tool therefore
keeps the same PID, starttime and namespace; only ``cmdline_sha`` changes
because ``/proc/<pid>/cmdline`` now shows the new program.

The old binding fingerprint ``(starttime, pid_ns, cmdline_sha)`` treated that
ordinary exec as ``identity_lost`` and fail-closed killed a healthy arm. A
genuine PID reuse, by contrast, cannot reproduce the bound starttime (or the
bound namespace). So the two cases are separable using immutable kernel facts
alone.

This module binds the exact CID (already cross-checked against ``podman
inspect {{.Id}}`` by :mod:`binding`) to the init PID reported by inspect, plus
its kernel starttime and namespace. The PID is an observation anchor for
``/proc`` reads **only**: no API here ever signals a bare PID. All teardown
stays CID-only in :mod:`teardown`.

``cmdline_sha`` is deliberately not identity. It is retained as a volatile
observation so a receipt can show *why* an identity check passed or failed.

Fail-closed semantics are unchanged: an unreadable record is
``measurement_unavailable``; a missing record, a changed starttime, a changed
namespace or an inspection mismatch is ``identity_lost``. No retry policy is
relaxed.
"""
from .errors import GuardExceeded

# Immutable kernel facts only. Never put a volatile cmdline hash here.
STABLE_KEYS = ("starttime", "pid_ns")


def stable_fingerprint(record):
    """Return the immutable ``(starttime, pid_ns)`` pair for a /proc record."""
    if record is None or any(record.get(key) is None for key in STABLE_KEYS):
        raise GuardExceeded("binding_unavailable")
    return (record["starttime"], record["pid_ns"])


def bind(cid, pid, record, *, cid_verified=True):
    """Bind exact CID + init PID to immutable kernel identity.

    ``pid`` comes from ``podman inspect {{.State.Pid}}`` for ``cid`` and is
    used solely to locate the process in a later /proc snapshot. ``cid_verified``
    asserts that inspection also returned ``{{.Id}} == cid``; a mismatch fails
    closed as ``identity_lost`` (never an assumed good binding).
    """
    if not cid_verified:
        raise GuardExceeded("identity_lost")
    if pid is None or int(pid) <= 0:
        raise GuardExceeded("binding_unavailable")
    stable = stable_fingerprint(record)
    bound = {
        "cid": cid,
        "pid": int(pid),
        "stable": True,
        # Stable fingerprint (two immutable kernel facts). Kept under the
        # conventional key so lease/receipt holders can carry it unchanged.
        "fingerprint": list(stable),
        "starttime": stable[0],
        "pid_ns": stable[1],
        # Volatile diagnosis only -- explicitly NOT part of identity.
        "cmdline_sha": record.get("cmdline_sha"),
    }
    bound["bind_observation"] = observation(bound, {int(pid): record})
    return bound


def locate(binding, table, *, bound_pid=None):
    """Locate the bound init process and confirm its immutable identity.

    The bound PID selects the candidate for a read-only ``/proc`` lookup.
    Confirmation uses ``starttime`` and ``pid_ns`` only, so a normal exec that
    changes ``cmdline_sha`` keeps the binding. PID reuse changes ``starttime``
    (or the namespace) and fails closed. No signal is ever sent to ``pid``.
    """
    pid = bound_pid if bound_pid is not None else binding.get("pid")
    if pid is None:
        raise GuardExceeded("binding_unavailable")
    record = table.get(pid)
    if record is None:
        raise GuardExceeded("identity_lost")
    if any(record.get(key) is None for key in STABLE_KEYS):
        raise GuardExceeded("measurement_unavailable")
    expected = (binding.get("starttime"), binding.get("pid_ns"))
    if expected == (None, None):
        # Fall back to the carried stable fingerprint for older callers.
        finger = binding.get("fingerprint")
        if finger is not None and len(finger) >= 2:
            expected = (finger[0], finger[1])
    if (record["starttime"], record["pid_ns"]) != expected:
        raise GuardExceeded("identity_lost")
    return pid


def observation(binding, table):
    """Return a receipt-ready record of bound vs last-observed identity.

    This is the missing instrumentation: with both sides recorded, a receipt
    can tell a normal exec (``cmdline_changed`` true, ``identity_matches``
    true) from PID reuse (``identity_matches`` false) without assuming either.
    """
    pid = binding.get("pid")
    bound = {"starttime": binding.get("starttime"),
             "pid_ns": binding.get("pid_ns"),
             "cmdline_sha": binding.get("cmdline_sha")}
    if binding.get("fingerprint") is not None and bound["starttime"] is None:
        finger = binding["fingerprint"]
        if len(finger) >= 2:
            bound["starttime"], bound["pid_ns"] = finger[0], finger[1]
    record = table.get(pid) if pid is not None else None
    if record is None:
        return {"bound": bound, "observed": {"pid": pid, "present": False}}
    observed = {"pid": pid, "present": True,
                "starttime": record.get("starttime"),
                "pid_ns": record.get("pid_ns"),
                "cmdline_sha": record.get("cmdline_sha")}
    observed["identity_matches"] = (
        observed["starttime"] == bound["starttime"] and
        observed["pid_ns"] == bound["pid_ns"])
    observed["cmdline_changed"] = (
        bound["cmdline_sha"] is not None and
        observed["cmdline_sha"] is not None and
        bound["cmdline_sha"] != observed["cmdline_sha"])
    return {"bound": bound, "observed": observed}
