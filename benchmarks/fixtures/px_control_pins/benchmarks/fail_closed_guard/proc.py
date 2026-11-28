"""Real /proc snapshot. Unavailable RSS stays None, never zero.

Each field is read independently. In particular, an unreadable ``status``
(VmRSS) must NOT discard an otherwise readable ``stat`` / ``ns/pid`` record:
the child keeps its structural identity (ppid, starttime, pid_ns) so
``tree.members`` still counts it and ``tree.rss_bytes`` fails closed with
``measurement_unavailable`` instead of silently dropping a large-RSS member.
"""
import hashlib
import os
from pathlib import Path


def _record(entry):
    """Read one /proc entry, preserving every fact that could be read.

    ``structural_unavailable`` is True only when the immutable identity facts
    themselves could not be read; a null ``rss`` with intact identity is a
    measurement gap, not an identity gap, and is handled by ``tree.rss_bytes``.
    """
    record = {"pid": int(entry.name), "ppid": None, "pgid": None,
              "starttime": None, "pid_ns": None, "cmdline_sha": None,
              "rss": None, "cgroup": None, "structural_unavailable": False}
    try:
        after = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        record["ppid"] = int(after[1])
        record["pgid"] = int(after[2])  # stat field 5, exact process group
        record["starttime"] = int(after[19])  # stat field 22
    except (OSError, ValueError, IndexError):
        pass
    try:
        record["pid_ns"] = os.stat(entry / "ns" / "pid").st_ino
    except OSError:
        pass
    try:
        record["cmdline_sha"] = hashlib.sha256(
            (entry / "cmdline").read_bytes()).hexdigest()
    except OSError:
        pass
    try:
        for line in (entry / "status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    record["rss"] = int(parts[1]) * 1024
                break
    except OSError:
        pass
    try:
        record["cgroup"] = (entry / "cgroup").read_text().strip()
    except OSError:
        pass
    if any(record[key] is None for key in ("ppid", "starttime", "pid_ns")):
        record["structural_unavailable"] = True
    return record


def snapshot(root="/proc"):
    """Return {pid: record}; unreadable RSS is null, structural facts survive."""
    table = {}
    for entry in Path(root).iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            table[pid] = _record(entry)
        except (OSError, ValueError, IndexError):
            table[pid] = {"pid": pid, "ppid": None, "pgid": None,
                          "starttime": None, "pid_ns": None,
                          "cmdline_sha": None, "rss": None, "cgroup": None,
                          "structural_unavailable": True}
    return table
