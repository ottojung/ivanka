"""Source-only P1 guarded-RSS adapter (prospective; NOT deployed).

Replaces pilot_5966811.py's tree_rss(proc.pid), which measured only the
Podman launcher process tree and was mislabelled whole_container_process_tree.
This module binds the exact issued CID to the container init PID reported by
`podman inspect {{.State.Pid}}`, verifies immutable kernel identity
(starttime + PID namespace inode) on every sample, sums RSS over the whole
container tree (same namespace UNION PPID descendants), and proves exact-CID
teardown on every exit path. No bare PID is ever signalled.

Kernel enforcement remains false: this is an observed, fail-closed userspace
bound, not a hard cap. Nothing here edits the live guard, a frozen receipt, an
image, MiCall or PX state.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

CID_RE = re.compile(r"[0-9a-f]{64}\Z")


class GuardError(Exception):
    """Fail-closed guard outcome. `reason` is receipt-ready."""

    def __init__(self, reason, *, result=None):
        super().__init__(reason)
        self.reason = reason
        self.result = result or {}


def _result(binding, peak, teardown, scope="whole_container_process_tree"):
    return {
        "schema": "ivanka.p1.p1guard.result.v1",
        "cid": binding.get("cid") if binding else None,
        "peak_rss_bytes": peak,
        "rss_sample_scope": scope,
        "kernel_enforcement": False,
        "enforcement": "userspace_observed_fail_closed",
        "teardown": teardown,
        "method": "exact_cid_to_init_pid_starttime_pidns_bound_tree_sampled_rss",
        "version": "ivanka.p1.p1guard.v1",
    }


def read_cid(cidfile):
    """Read a plain, non-symlink 64-hex CID file or fail closed."""
    path = Path(cidfile)
    if path.is_symlink() or not path.is_file():
        raise GuardError("binding_unavailable")
    cid = path.read_text().strip()
    if not CID_RE.fullmatch(cid):
        raise GuardError("binding_unavailable")
    return cid


def snapshot(root="/proc"):
    """Real /proc table; unreadable fields stay None, never zero."""
    table = {}
    for entry in Path(root).iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            after = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            rec = {
                "pid": pid,
                "ppid": int(after[1]),
                "starttime": int(after[19]),
                "pid_ns": os.stat(entry / "ns" / "pid").st_ino,
                "cmdline_sha": hashlib.sha256((entry / "cmdline").read_bytes()).hexdigest(),
                "rss": None,
            }
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        rec["rss"] = int(parts[1]) * 1024
                    break
            table[pid] = rec
        except (OSError, ValueError, IndexError):
            table[pid] = {"pid": pid, "ppid": None, "starttime": None,
                          "pid_ns": None, "cmdline_sha": None, "rss": None}
    return table


def bind_container(cid, inspect, snap=None):
    """Bind exact CID -> init PID -> immutable (starttime, pid_ns)."""
    if not CID_RE.fullmatch(cid):
        raise GuardError("binding_unavailable")
    info = inspect(cid)
    if not info or info.get("id") != cid or not isinstance(info.get("pid"), int):
        raise GuardError("identity_lost")
    table = snap if snap is not None else snapshot()
    rec = table.get(info["pid"])
    if rec is None:
        raise GuardError("identity_lost")
    if rec.get("starttime") is None or rec.get("pid_ns") is None:
        raise GuardError("measurement_unavailable")
    return {"cid": cid, "pid": info["pid"], "starttime": rec["starttime"],
            "pid_ns": rec["pid_ns"], "cmdline_sha": rec.get("cmdline_sha"),
            "fingerprint": (rec["starttime"], rec["pid_ns"])}


def locate(binding, table):
    """Re-find the bound init task by immutable identity (PID reuse safe)."""
    pid = binding.get("pid")
    rec = table.get(pid)
    if rec is None:
        raise GuardError("identity_lost")
    if rec.get("starttime") is None or rec.get("pid_ns") is None:
        raise GuardError("measurement_unavailable")
    if (rec["starttime"], rec["pid_ns"]) != tuple(binding["fingerprint"]):
        raise GuardError("identity_lost")
    return pid


def members(table, pid, binding):
    """Whole container tree = same PID namespace UNION PPID descendants."""
    ns = table[pid].get("pid_ns")
    if ns is None or ns != binding["pid_ns"]:
        raise GuardError("identity_lost" if ns is not None else "measurement_unavailable")
    same_ns = {p for p, r in table.items() if r.get("pid_ns") == ns}
    group = set(same_ns)
    while True:
        extra = {p for p, r in table.items() if r.get("ppid") in group and p not in group}
        if not extra:
            return group
        group |= extra


def rss_bytes(table, pids):
    """Conservative sum: a single unreadable RSS makes the sample null."""
    values = [table[p].get("rss") for p in pids if p in table]
    if not values or any(v is None for v in values):
        raise GuardError("measurement_unavailable")
    return sum(values)


def check_disk(path, reserve_bytes, disk_usage=None):
    """Fail closed on unreadable disk state or short reserve."""
    try:
        free = (disk_usage or shutil.disk_usage)(str(path)).free
    except Exception as exc:
        raise GuardError("measurement_unavailable") from exc
    if free < reserve_bytes:
        raise GuardError("reserve_shortfall")
    return free


def watch(binding, *, limit, wall_seconds, running, snap, measure,
          stop, clock=time.monotonic, sleep=time.sleep, audit=None,
          interval=0.5, start=None):
    """Sample the bound whole-container tree; exact-CID teardown on all paths."""
    if limit <= 0 or wall_seconds <= 0 or interval <= 0:
        raise GuardError("invalid_config")
    started = clock() if start is None else start
    peak = None
    teardown = None
    stopped = False
    cid = binding["cid"]

    def emit(event):
        if audit is not None:
            audit({**event, "schema": "ivanka.p1.p1guard.event.v1", "cid": cid})

    def stop_once():
        nonlocal teardown, stopped
        if not stopped:
            teardown = stop(cid)  # CID-only, must include absence proof
            stopped = True
        return teardown

    try:
        while running():
            if clock() - started >= wall_seconds:
                raise GuardError("wall_limit")
            table = snap()
            pid = locate(binding, table)
            group = members(table, pid, binding)
            used = rss_bytes(table, group)
            peak = used if peak is None else max(peak, used)
            if used > limit:
                emit({"reason": "observed_rss_limit", "rss_bytes": used,
                      "members": len(group), "kernel_enforcement": False})
                stop_once()
                raise GuardError("observed_rss_limit")
            if measure() is None:
                raise GuardError("measurement_unavailable")
            sleep(interval)
    except GuardError as exc:
        proof = stop_once()
        exc.result = _result(binding, peak, proof)
        raise
    except Exception as exc:
        # Launcher death / killed monitor / unreadable measurement is never
        # a scientific result and never an invented zero-byte sample.
        proof = stop_once()
        guarded = GuardError("measurement_unavailable")
        guarded.result = _result(binding, peak, proof)
        raise guarded from exc
    proof = stop_once()
    return _result(binding, peak, proof)


def append_lease(path, event):
    """Durable append+fsync lease/CID journal record."""
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def recover_lease(path):
    """Refuse admission while a prior owned lease has no matching close."""
    p = Path(path)
    if not p.is_file():
        return []
    events = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    open_events = []
    for ev in events:
        if ev.get("event") == "acquired":
            open_events.append(ev)
        elif ev.get("event") == "released" and open_events:
            open_events.pop()
    return open_events


def release_stop(path, proof, lease_path, owner):
    """Only the owner may retire STOP, and only after teardown proof.

    `proof` must assert exact-CID removal and a fresh absence check.
    """
    p = Path(path)
    if not p.is_file():
        raise GuardError("stop_absent")
    if not proof or proof.get("container_removed") is not True or proof.get("fresh_absence_check") is not True:
        raise GuardError("teardown_unverified")
    append_lease(lease_path, {"event": "stop_retired", "owner": owner,
                              "cid": proof.get("cid"), "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    p.unlink()
    append_lease(lease_path, {"event": "released", "owner": owner,
                              "cid": proof.get("cid"), "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
