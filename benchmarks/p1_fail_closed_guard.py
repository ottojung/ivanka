"""Self-contained fail-closed userspace RSS guard for the two diagnostic arms.

Modelled on the reviewed PR473/PR474 guard contract: exact CID binding,
identity-bound /proc sampling, null RSS is never zero, one wall deadline for
binding plus sampling, and teardown by exact CID with before/after proof.
No process is signalled by bare PID. On this host the OCI `--memory` setting is
configured but not kernel-enforced (read-only, undelegated cgroup), so this is
userspace observation, not a hard kernel cap.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import time
from typing import Any, Callable

CID = re.compile(r"[0-9a-f]{64}\Z")
RSS_LIMIT = 4_000_000_000
SAMPLE_INTERVAL = 0.5


class GuardExceeded(Exception):
    """Unsafe, unavailable or over-budget observation: terminal arm failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def command(argv: list[str], env: dict[str, str] | None = None, timeout: int = 15) -> str:
    return subprocess.run(
        argv, env=env or os.environ.copy(), check=True, capture_output=True,
        text=True, timeout=timeout,
    ).stdout.strip()


def proc_snapshot(root: str = "/proc") -> dict[int, dict[str, Any]]:
    """Return {pid: record}; an unreadable entry has null RSS, never zero."""
    table: dict[int, dict[str, Any]] = {}
    for entry in pathlib.Path(root).iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            after = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            rss = None
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        rss = int(parts[1]) * 1024
                    break
            table[pid] = {
                "pid": pid,
                "ppid": int(after[1]),
                "starttime": int(after[19]),
                "pid_ns": os.stat(entry / "ns" / "pid").st_ino,
                "cmdline_sha": hashlib.sha256((entry / "cmdline").read_bytes()).hexdigest(),
                "rss": rss,
            }
        except (OSError, ValueError, IndexError):
            table[pid] = {
                "pid": pid, "ppid": None, "starttime": None, "pid_ns": None,
                "cmdline_sha": None, "rss": None,
            }
    return table


def fingerprint(record: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (record["starttime"], record["pid_ns"], record["cmdline_sha"])


def locate(finger: tuple[Any, Any, Any], table: dict[int, dict[str, Any]]) -> int:
    matches = [pid for pid, record in table.items() if fingerprint(record) == finger]
    if len(matches) != 1:
        raise GuardExceeded("identity_lost")
    return matches[0]


def descendants(table: dict[int, dict[str, Any]], anchor: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, record in table.items():
        parent = record.get("ppid")
        if parent is not None:
            children.setdefault(parent, []).append(pid)
    found: set[int] = set()
    pending = [anchor]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(children.get(current, []))
    return found


def rss_bytes(table: dict[int, dict[str, Any]], pids: set[int]) -> int:
    values = [table[pid].get("rss") for pid in pids if pid in table]
    if any(value is None for value in values):
        raise GuardExceeded("measurement_unavailable")
    return sum(values)


def bind_container(
    cid: str, env: dict[str, str] | None = None,
    snapshot: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    out = command(
        ["podman", "inspect", "--format", "{{.Id}} {{.State.Pid}}", cid], env
    )
    fields = out.split()
    if len(fields) != 2 or fields[0] != cid:
        raise GuardExceeded("identity_lost")
    pid = int(fields[1])
    table = snapshot if snapshot is not None else proc_snapshot()
    record = table.get(pid)
    if record is None or any(
        record.get(key) is None for key in ("starttime", "pid_ns", "cmdline_sha")
    ):
        raise GuardExceeded("binding_unavailable")
    return {"cid": cid, "pid": pid, "fingerprint": fingerprint(record)}


def bind_by_name(
    name: str, env: dict[str, str] | None = None,
    snapshot: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cid = command(["podman", "inspect", "--format", "{{.Id}}", name], env)
    return bind_container(cid, env, snapshot=snapshot)


def observe(
    bound: dict[str, Any], snapshot: dict[int, dict[str, Any]] | None = None,
) -> int:
    table = snapshot if snapshot is not None else proc_snapshot()
    pid = locate(bound["fingerprint"], table)
    namespace = table[pid].get("pid_ns")
    if namespace is None:
        raise GuardExceeded("measurement_unavailable")
    group = {
        member for member, record in table.items()
        if record.get("pid_ns") == namespace
    } | descendants(table, pid)
    return rss_bytes(table, group)


def listed_cids(env: dict[str, str] | None = None) -> list[str]:
    return command(
        ["podman", "ps", "-a", "--no-trunc", "--format", "{{.ID}}"], env
    ).splitlines()


def stop_cid(
    cid: str, env: dict[str, str] | None = None, timeout: int = 45,
    listed: Callable[[], list[str]] | None = None,
) -> dict[str, Any]:
    """Idempotent exact-CID removal with before/after absence proof."""
    if not CID.fullmatch(cid):
        raise GuardExceeded("invalid_cid")
    names = listed or (lambda: listed_cids(env))
    was_present = cid in names()
    if was_present:
        subprocess.run(
            ["podman", "rm", "-f", cid], env=env or os.environ.copy(),
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    if cid in names():
        raise GuardExceeded("container_survived")
    return {
        "cid": cid, "container_removed": was_present,
        "fresh_absence_check": True, "kernel_enforcement": False,
    }


def watch(
    bound: dict[str, Any], *, limit: int, deadline: float,
    running: Callable[[], bool],
    observe_fn: Callable[[dict[str, Any]], int] | None = None,
    snapshot_fn: Callable[[], dict[int, dict[str, Any]]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    interval: float = SAMPLE_INTERVAL,
) -> int | None:
    """One deadline covers binding and sampling; no sample is a null success."""
    if limit <= 0 or deadline <= 0 or interval <= 0:
        raise GuardExceeded("invalid_config")
    now = clock or time.monotonic
    sleep = sleep_fn or time.sleep
    sampler = observe_fn or (lambda bound: observe(bound, (snapshot_fn or proc_snapshot)()))
    peak: int | None = None
    while running():
        if now() >= deadline:
            raise GuardExceeded("wall_limit")
        try:
            used = sampler(bound)
        except GuardExceeded:
            raise
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable") from exc
        peak = used if peak is None else max(peak, used)
        if used > limit:
            raise GuardExceeded("observed_rss_limit")
        sleep(interval)
    return peak
