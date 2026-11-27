"""Namespace-complete membership and conservative RSS summation."""
from .errors import GuardExceeded

# /proc/<pid>/stat field 3. A zombie has already released its resident pages;
# only a state positively read as Z may contribute a zero RSS observation.
ZOMBIE_STATE = "Z"


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
    """Conservative sum: only a proven zombie may contribute zero RSS.

    A null RSS from ``proc.snapshot`` is a measurement gap, not a zero-byte
    reading, and still fails closed. The sole exception is a member whose
    ``state`` was actually read from /proc stat as ``Z``: a zombie has no
    resident pages, so counting it as zero neither hides live memory nor
    admits a fabricated observation. A live, unreadable, or ambiguous member
    (missing/unknown state) keeps the whole sample ``measurement_unavailable``.
    """
    total = 0
    measured = False
    for pid in pids:
        record = table.get(pid)
        if record is None:
            continue
        value = record.get("rss")
        if value is None:
            if record.get("state") != ZOMBIE_STATE:
                raise GuardExceeded("measurement_unavailable")
            value = 0
        total += value
        measured = True
    if not measured:
        raise GuardExceeded("measurement_unavailable")
    return total
