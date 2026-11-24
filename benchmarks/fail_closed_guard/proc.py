"""Real /proc snapshot. Unavailable RSS stays None, never zero."""
import hashlib
import os
from pathlib import Path


def _record(entry):
    after = (entry / "stat").read_text().rsplit(")", 1)[1].split()
    ppid = int(after[1])
    starttime = int(after[19])  # stat field 22
    ns = os.stat(entry / "ns" / "pid").st_ino
    cmdline = (entry / "cmdline").read_bytes()
    rss = None
    for line in (entry / "status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                rss = int(parts[1]) * 1024
            break
    cgroup = (entry / "cgroup").read_text().strip()
    return {"pid": int(entry.name), "ppid": ppid, "starttime": starttime,
            "pid_ns": ns, "cmdline_sha": hashlib.sha256(cmdline).hexdigest(),
            "rss": rss, "cgroup": cgroup}


def snapshot(root="/proc"):
    """Return {pid: record}; unreadable processes get a null observation."""
    table = {}
    for entry in Path(root).iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            table[pid] = _record(entry)
        except (OSError, ValueError, IndexError):
            table[pid] = {"pid": pid, "ppid": None, "starttime": None,
                          "pid_ns": None, "cmdline_sha": None,
                          "rss": None, "cgroup": None}
    return table
