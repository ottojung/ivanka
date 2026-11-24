"""Identity binding: never sample or signal a bare reused PID."""
from .errors import GuardExceeded


def fingerprint(record):
    return (record["starttime"], record["pid_ns"], record["cmdline_sha"])


def locate(finger, table):
    """Exactly one live process must carry the bound identity."""
    matches = [pid for pid, record in table.items()
               if fingerprint(record) == finger]
    if len(matches) != 1:
        raise GuardExceeded("identity_lost")
    return matches[0]


def bind(record):
    if any(record.get(key) is None for key in
           ("starttime", "pid_ns", "cmdline_sha")):
        raise GuardExceeded("binding_unavailable")
    return fingerprint(record)
