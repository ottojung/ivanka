"""Fail closed on large benchmark process trees when cgroups are unavailable."""
import hashlib
import json
import os
from pathlib import Path
import time

from benchmarks.memory_guard.signals import enforce
from benchmarks.memory_guard.proc import (
    LIMIT, TRIP, benchmark_roots, processes, tree_bytes,
)

INTERVAL_SECONDS = 0.1
LOG = Path(os.environ.get(
    "IVANKA_GUARD_LOG",
    "/workspace/micall-frozen-seven-20261117/cap-4gb-memory-violations.jsonl"))


def audit(pid, resident, cmd, action):
    event = {"schema": "ivanka.observable-memory-guard.v1",
             "observed_utc": time.time(), "pid": pid,
             "command_sha256": hashlib.sha256(cmd.encode()).hexdigest(),
             "rss_tree_bytes": resident, "soft_trip_bytes": TRIP,
             "memory_max_bytes": LIMIT, "action": action}
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def watch():
    signaled = {}
    while True:
        table = processes()
        signaled = {p: v for p, v in signaled.items() if p in table}
        for pid in benchmark_roots(table):
            used, members = tree_bytes(table, pid)
            if used < TRIP:
                continue
            enforce(pid, members, table[pid][2], used, signaled, audit)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    watch()
