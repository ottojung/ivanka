"""Identity binding: never sample or signal a bare reused PID."""
from .errors import GuardExceeded


def fingerprint(record):
    return (record["starttime"], record["pid_ns"], record["cmdline_sha"])


def locate(finger, table, bound_pid=None):
    """Exactly one live process must carry the bound identity.

    A transient /proc read failure is represented by a null record; that is
    an unreadable observation (measurement_unavailable), not a proven
    identity loss. The caller provides bound_pid so an unreadable bound
    process is distinguished from a missing one.
    """
    matches = [pid for pid, record in table.items()
               if fingerprint(record) == finger]
    if len(matches) == 1:
        return matches[0]
    if bound_pid is not None and bound_pid in table:
        record = table[bound_pid]
        if any(record.get(key) is None for key in
               ("starttime", "pid_ns", "cmdline_sha")):
            raise GuardExceeded("measurement_unavailable")
    raise GuardExceeded("identity_lost")


def bind(record):
    if any(record.get(key) is None for key in
           ("starttime", "pid_ns", "cmdline_sha")):
        raise GuardExceeded("binding_unavailable")
    return fingerprint(record)
