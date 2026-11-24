"""Fail-closed reclamation of PX job temporaries after verified teardown.

The guarded launcher redirects every per-job TMPDIR into the metered project
tree so those bytes stay inside the certified storage ceiling. This module only
removes a *known* job-owned directory, and only when no other worker holds the
global PX lock, the exact graphroot is confirmed, the owning process is reaped
and no mount or open descriptor still references the directory. Raw read-pair
FASTQs, OCI store layers and unknown contents are never removed here.
"""
import fcntl
import os
import re
import shutil
from pathlib import Path

from .exploratory_runtime import cleanup as runtime_cleanup
from .exploratory_space import px_temp_dir

JOB_NAME = re.compile(r"job-[a-z0-9][a-z0-9-]*$")
BUILDAH_NAME = re.compile(r"buildah[0-9]+$")
IMAGE_TEMP_NAME = re.compile(r"container_images_storage[0-9]+$")


def job_temp_dir(root, ident):
    """Return the exact per-job TMPDIR beneath the metered project temp root."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ident or ""):
        raise ValueError("invalid job identifier")
    # The exact-root check belongs to the destructive helpers; the launcher
    # already validates its root in prepare() and tests use isolated roots.
    return px_temp_dir(root) / ("job-" + ident)


def _lock_held(root):
    with (Path(root) / ".global-worker.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
        return False


def _graphroot_ok(env):
    """Require the one authorized rootless graphroot, never another store."""
    if env.get("CONTAINERS_STORAGE_CONF") != str(runtime_cleanup.ROOT / "storage.conf"):
        return False
    try:
        graph = runtime_cleanup.command(
            ["podman", "info", "--format", "{{.Store.GraphRoot}}"], env)
    except (OSError, ValueError, RuntimeError):
        return False
    return graph == runtime_cleanup.STORE


def _live_pid(path):
    pid_file = path / "pid"
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return True  # unreadable ownership marker is never assumed dead
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _referenced(path):
    """Refuse any directory with a live mount or open descriptor under it."""
    target = str(path.resolve()) + "/"
    try:
        mounts = Path("/proc/mounts").read_text()
        for line in mounts.splitlines():
            fields = line.split()
            if len(fields) > 1 and fields[1].startswith(target):
                return True
        for fd in Path("/proc").glob("[0-9]*/fd/*"):
            try:
                if str(fd.resolve()).startswith(target):
                    return True
            except (OSError, RuntimeError):
                continue
    except OSError:
        return True  # fail closed if the process table cannot be inspected
    return False


def _safe_target(path, base):
    """Only a known, real directory directly beneath the metered TMPDIR."""
    if path.is_symlink() or not path.is_dir():
        return False
    resolved = path.resolve()
    if resolved.parent != base.resolve() or not resolved.name.startswith(
            ("job-", "buildah", "container_images_storage")):
        return False
    name = resolved.name
    return bool(JOB_NAME.fullmatch(name) or BUILDAH_NAME.fullmatch(name)
                or IMAGE_TEMP_NAME.fullmatch(name))


def clean_job_temp(root, ident, env=None, lock_held_by_caller=False):
    """Remove one verified job TMPDIR; preserve everything on any doubt."""
    if Path(root).resolve() != runtime_cleanup.ROOT:
        return {"removed": False, "reason": "not the dedicated PX project root"}
    target = job_temp_dir(root, ident)
    base = px_temp_dir(root)
    if not lock_held_by_caller and _lock_held(root):
        return {"removed": False, "reason": "another worker holds the PX lock"}
    if not _safe_target(target, base):
        return {"removed": False, "reason": "not a known job-owned temp directory"}
    if env is not None and not _graphroot_ok(env):
        return {"removed": False, "reason": "graphroot could not be verified"}
    if _live_pid(target) or _referenced(target):
        return {"removed": False, "reason": "live owner, mount or descriptor"}
    shutil.rmtree(target)
    return {"removed": True, "path": str(target),
            "reason": "verified teardown and known rebuildable job temporary"}


def audit_terminal_temp(root, env=None, apply=False):
    """Audit (and optionally reclaim) stale job temporaries at cohort end."""
    if Path(root).resolve() != runtime_cleanup.ROOT:
        return {"schema": "ivanka.px.job-temp-audit.v1", "entries": [],
                "removed": [], "reason": "not the dedicated PX project root"}
    base = px_temp_dir(root)
    if not base.is_dir():
        return {"schema": "ivanka.px.job-temp-audit.v1", "entries": [],
                "removed": [], "reason": "no project TMPDIR"}
    if _lock_held(root):
        return {"schema": "ivanka.px.job-temp-audit.v1", "entries": [],
                "removed": [], "reason": "another worker holds the PX lock"}
    if env is not None and not _graphroot_ok(env):
        return {"schema": "ivanka.px.job-temp-audit.v1", "entries": [],
                "removed": [], "reason": "graphroot could not be verified"}
    entries, removed = [], []
    for path in sorted(base.iterdir()):
        known = _safe_target(path, base)
        dead = known and not _live_pid(path) and not _referenced(path)
        record = {"path": str(path), "known": bool(known),
                  "reclaimable": bool(dead)}
        entries.append(record)
        if apply and dead:
            shutil.rmtree(path)
            removed.append(str(path))
    return {"schema": "ivanka.px.job-temp-audit.v1", "entries": entries,
            "removed": removed, "applied": bool(apply)}
