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


def members(table, anchor_pid, finger=None):
    """Same-PID-namespace UNION PPID descendants of the bound init task.

    A child whose VmRSS was unreadable keeps its structural identity from
    ``proc.snapshot`` (ppid/starttime/pid_ns) and therefore remains in this
    set; ``rss_bytes`` then fails closed rather than hiding its RSS from the
    sum. A task whose structural identity could not be read at all cannot be
    excluded when it shares the bound container's cgroup, so that case fails
    closed too -- unrelated host processes (different cgroup) are ignored.
    """
    if anchor_pid not in table:
        raise GuardExceeded("identity_lost")
    anchor = table[anchor_pid]
    namespace = anchor.get("pid_ns")
    if namespace is None:
        raise GuardExceeded("measurement_unavailable")
    same_ns = {pid for pid, record in table.items()
               if record.get("pid_ns") == namespace}
    group = same_ns | descendants(table, anchor_pid)
    anchor_cgroup = anchor.get("cgroup")
    if anchor_cgroup:
        for pid, record in table.items():
            if pid in group or not record.get("structural_unavailable"):
                continue
            if record.get("cgroup") == anchor_cgroup:
                raise GuardExceeded("measurement_unavailable")
    return group


def rss_bytes(table, pids):
    """Conservative sum: one unreadable/null RSS makes the whole sample null."""
    values = [table[pid].get("rss") for pid in pids if pid in table]
    if not values or any(value is None for value in values):
        raise GuardExceeded("measurement_unavailable")
    return sum(values)
