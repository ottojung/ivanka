"""Read-only live service attestation for PX guard cutover.

This inspects s6 persistent/runtime pins, /proc identity and lease state. It
never mutates services, files, leases, receipts or registry. A source-byte
match alone is not live attestation; this module reports both.
"""
import json
import os
from pathlib import Path

from . import px_guard_source as guard_source


def _read(path):
    p = Path(path)
    return p.read_text() if p.is_file() else None


def _proc(pid):
    proc = Path("/proc") / str(int(pid))
    if not proc.is_dir():
        return None
    cmd = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
    env = {}
    for item in (proc / "environ").read_bytes().split(b"\x00"):
        if b"=" in item:
            k, v = item.split(b"=", 1)
            env[k.decode(errors="replace")] = v.decode(errors="replace")
    try:
        cwd = os.readlink(proc / "cwd")
    except OSError:
        cwd = None
    return {"pid": int(pid), "cmdline": cmd, "cwd": cwd, "environ": env}


def _flock_locked(path):
    import fcntl
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


def _active_lease(lease_path):
    p = Path(lease_path)
    if not p.is_file():
        return {"present": False, "active": False}
    active = None
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return {"present": True, "active": True, "error": "unreadable"}
        if row.get("state") == "active":
            active = row
        elif row.get("state") == "released" and active and row.get("lease") == active.get("lease"):
            active = None
    return {"present": True, "active": active is not None, "lease": active}


def attest(*, watchdog_pid=None, supervisor_pid=None,
           persistent_watchdog="/etc/services.d/ivanka-watchdog/run",
           runtime_watchdog="/run/s6/legacy-services/ivanka-watchdog/run",
           persistent_supervisor="/etc/services.d/px-cohort-supervisor/run",
           runtime_supervisor="/run/s6/legacy-services/px-cohort-supervisor/run",
           global_lock="/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock",
           worker_lease="/workspace/ivanka-exploratory-ten-20261121/.worker-lease.jsonl"):
    report = {"kind": "px.live.attestation.read_only.v1", "blockers": [], "checks": {}}
    for name, path in [("persistent_watchdog", persistent_watchdog),
                       ("runtime_watchdog", runtime_watchdog),
                       ("persistent_supervisor", persistent_supervisor),
                       ("runtime_supervisor", runtime_supervisor)]:
        text = _read(path)
        report["checks"][name] = {"path": path, "present": text is not None}
        if text is None:
            report["blockers"].append(f"missing:{name}")
        else:
            report["checks"][name]["mentions_deployed_head"] = guard_source.DEPLOYED_HEAD in text
            report["checks"][name]["mentions_old_head"] = "091f56275ae823cb3291b81dbdf016fcf16c3ea0" in text
    for label, pid, code_key in [("watchdog", watchdog_pid, "WATCHDOG_CODE"),
                                 ("supervisor", supervisor_pid, "PX_CODE")]:
        proc = _proc(pid) if pid is not None else None
        check = {"pid": pid, "present": proc is not None}
        if proc is None:
            report["blockers"].append(f"missing_proc:{label}")
        else:
            code = proc["environ"].get(code_key)
            check["code_root"] = code
            check["pythonpath"] = proc["environ"].get("PYTHONPATH")
            if code:
                code_path = Path(code)
                check["code_root_exists"] = code_path.exists()
                if (code_path / ".git").exists():
                    try:
                        head = guard_source._git_head(code_path)
                    except ValueError:
                        head = None
                    check["code_head"] = head
                try:
                    modules = guard_source.verify_deployment(code_path)["modules"]
                    check["staged_bytes_match_expected"] = modules == dict(guard_source.EXPECTED)
                except Exception as exc:
                    check["staged_bytes_match_expected"] = False
                    check["bytes_error"] = str(exc)
            else:
                report["blockers"].append(f"missing_env:{label}:{code_key}")
        report["checks"][label] = check
    lock = Path(global_lock)
    lease = _active_lease(worker_lease)
    report["checks"]["global_lock"] = {"path": str(lock), "exists": lock.exists(),
                                       "locked": _flock_locked(lock) if lock.exists() else False}
    report["checks"]["worker_lease"] = lease
    if lease.get("active") or report["checks"]["global_lock"].get("locked"):
        report["blockers"].append("active_lease_or_lock")
    report["ready_for_cutover"] = len(report["blockers"]) == 0
    report["attests_live_process_identity"] = False  # bytes/pins evidence only; not kernel proof
    return report
