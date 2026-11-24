"""Namespace-complete membership and conservative RSS summation."""
from .errors import GuardExceeded


def descendants(table, root):
    members = {root}
    while True:
        extra = {pid for pid, record in table.items()
                 if record.get("ppid") in members and pid not in members}
        if not extra:
            return members
        members |= extra


def members(table, anchor_pid, finger):
    if anchor_pid not in table:
        raise GuardExceeded("identity_lost")
    namespace = table[anchor_pid].get("pid_ns")
    if namespace is None:
        raise GuardExceeded("measurement_unavailable")
    same_ns = {pid for pid, record in table.items()
               if record.get("pid_ns") == namespace}
    return same_ns | descendants(table, anchor_pid)


def rss_bytes(table, pids):
    values = [table[pid].get("rss") for pid in pids if pid in table]
    if any(value is None for value in values):
        raise GuardExceeded("measurement_unavailable")
    return sum(values)
