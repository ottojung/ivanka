"""Narrowly scoped COPY-only overlay build admission and teardown.

This path exists for reviewed binary-only overlays (one COPY layer on a frozen
base image). It is not a general build escape hatch: no RUN, ADD, remote
context, network, volume or inherited store is accepted, and it is supervised
by the same durable lease, exact process-group identity and independent
watchdog as a pilot. Nothing here is enabled by unsetting ``WATCHDOG_ARMED``.
"""
import hashlib
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from . import (build, disk, heartbeat, lease, orphans, proc, store, watchdog,
               watchdog_contract)
from .errors import GuardExceeded

SCHEMA = "ivanka.copy-overlay-plan.v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{7,64}\Z")
DESTINATION = re.compile(r"/opt/ivanka/bin/[A-Za-z0-9_.-]+\Z")
INTERVAL = 0.5


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def _safe_relative(value):
    path = Path(value)
    return (not path.is_absolute() and ".." not in path.parts
            and not any(part.startswith("/") for part in path.parts))


def validate_plan(plan, *, expected_base, expected_commit, root):
    """Return a normalised plan or fail closed before any process exists."""
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise GuardExceeded("invalid_plan")
    base = plan.get("base_image")
    commit = plan.get("source_commit")
    if (not isinstance(base, str) or not DIGEST.fullmatch(base)
            or base != expected_base
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)
            or commit != expected_commit):
        raise GuardExceeded("invalid_plan")
    context = Path(plan.get("context", ""))
    root_path = Path(root).resolve()
    try:
        resolved = context.resolve()
    except OSError as exc:
        raise GuardExceeded("invalid_plan") from exc
    if (context.is_symlink() or not context.is_dir()
            or root_path not in resolved.parents or resolved == root_path):
        raise GuardExceeded("invalid_plan")
    containerfile = context / "Containerfile"
    if containerfile.is_symlink() or not containerfile.is_file():
        raise GuardExceeded("invalid_plan")
    lines = containerfile.read_text().splitlines()
    if not lines or lines[0] != "FROM " + base:
        raise GuardExceeded("invalid_plan")
    copies = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 3 or fields[0] != "COPY":
            raise GuardExceeded("invalid_plan")
        source, destination = fields[1], fields[2]
        if (not _safe_relative(source) or not DESTINATION.fullmatch(destination)
                or "://" in source or source.startswith("/")):
            raise GuardExceeded("invalid_plan")
        artifact = context / source
        if artifact.is_symlink() or not artifact.is_file():
            raise GuardExceeded("invalid_plan")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        copies.append({"source": source, "destination": destination,
                       "sha256": digest})
    if not copies or plan.get("copies") != copies:
        raise GuardExceeded("invalid_plan")
    tag = plan.get("tag")
    if not isinstance(tag, str) or not re.fullmatch(
            r"ivanka-copy-[0-9a-f]{12,64}", tag):
        raise GuardExceeded("invalid_plan")
    argv = ["podman", "build", "--network=none", "--pull=never",
            "-f", str(containerfile), "-t", tag, str(resolved)]
    return {"schema": SCHEMA, "base_image": base, "source_commit": commit,
            "context": str(resolved), "containerfile": str(containerfile),
            "copies": copies, "tag": tag, "argv": argv,
            "plan_sha256": plan_digest(plan)}


@contextmanager
def shared_lock(root, *, blocking=False):
    """Use the same advisory worker lock as pilots and ordinary builds."""
    path = Path(root) / ".global-worker.lock"
    with path.open("a+") as handle:
        import fcntl
        mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(handle, mode)
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def default_spawn(root, argv, env, log):
    """Start one build in its own session so the PGID is exactly its PID."""
    with Path(log).open("xb") as output:
        return subprocess.Popen(
            argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True)


def _teardown(pgid, *, pinned, graphroot, snapshot, sleep, monotonic,
              command, stop=None, cleanup=None):
    terminate = stop if stop is not None else (
        lambda value: build.stop_group_by_id(value, snapshot=snapshot,
                                              sleep=sleep, clock=monotonic))
    reclaim = cleanup if cleanup is not None else (
        lambda: orphans.clean_pinned_storage(pinned, graphroot,
                                             command_fn=command))
    proof = terminate(pgid)
    proof["orphan_cleanup"] = reclaim()
    return proof


def run(root, plan, *, storage_conf, graphroot, expected_base, expected_commit,
        reserve_bytes, alive=None, env=None, owner=None, lock=None,
        wall_seconds=watchdog.DEFAULT_WALL_SECONDS,
        rss_limit=watchdog.RSS_LIMIT, wall=None, monotonic=None, sleep=None,
        snapshot=None, command=None, usage=None, spawn=None, stop=None,
        cleanup=None):
    """Admit and supervise one reviewed COPY-only overlay build.

    The caller supplies the already-acquired shared lock; readiness, lease
    clearance, store binding and disk reserve are rechecked under it. A crash
    before the post-spawn group bind leaves an active lease that blocks all
    further admission; a crash after it leaves a group the watchdog can stop.
    """
    if lock is None:
        raise GuardExceeded("shared_lock_required")
    wall = wall if wall is not None else time.time
    mono = monotonic if monotonic is not None else time.monotonic
    nap = sleep if sleep is not None else time.sleep
    take = snapshot if snapshot is not None else proc.snapshot
    command = command or orphans.command
    base_env = dict(env if env is not None else os.environ)
    pinned = store.pin_env(base_env, storage_conf=storage_conf)
    store.verify_namespace(pinned, graphroot)
    # No environment flag can relax the supported-mode or readiness contract.
    watchdog_contract.require_supported_mode("copy_overlay")
    alive = alive or heartbeat.alive_path(root)
    watchdog_contract.require_watchdog_readiness(
        alive, graphroot=graphroot, wall=wall, snapshot=take)
    lease.require_clear(root, pinned, watchdog_path=alive, graphroot=graphroot,
                        snapshot=take, wall=wall, command=command)
    disk.check_reserve(root, reserve_bytes, usage=usage)
    validated = validate_plan(plan, expected_base=expected_base,
                              expected_commit=expected_commit, root=root)
    ident = "copy-" + validated["plan_sha256"][:16]
    owner = str(owner or ident)
    lease.acquire(root, ident, "copy_overlay", owner=owner)
    emitter = heartbeat.Emitter(root, ident)
    emitter.before_spawn()
    log = Path(root) / ("run-" + ident + ".log")
    start = lease.acquisition_start(root, ident)
    deadline = start + min(wall_seconds, watchdog.DEFAULT_WALL_SECONDS)
    limit = min(rss_limit, watchdog.RSS_LIMIT)
    handle = None
    try:
        maker = spawn or (lambda argv, env_value: default_spawn(
            root, argv, env_value, log))
        handle = maker(validated["argv"], pinned)
        table = take()
        record = table.get(handle.pid)
        if record is None:
            raise GuardExceeded("binding_unavailable")
        fingerprint = build.bind_launcher(handle.pid, snapshot=table)[
            "fingerprint"]
        if record.get("pgid") != handle.pid:
            raise GuardExceeded("identity_lost")
        lease.bind_group(root, ident, handle.pid, handle.pid, fingerprint,
                         owner=owner, plan_sha256=validated["plan_sha256"],
                         graphroot=graphroot)
        observed_pid = watchdog.verify_group_bound(
            watchdog.bound_from_lease(root, ident, pinned), table)
        if observed_pid["rss"] > limit:
            raise GuardExceeded("observed_rss_limit")
        while handle.poll() is None:
            if wall() >= deadline:
                raise GuardExceeded("wall_limit")
            disk.check_reserve(root, reserve_bytes, usage=usage)
            emitter.refresh()
            nap(INTERVAL)
            table = take()
            observed = watchdog.verify_group_bound(
                watchdog.bound_from_lease(root, ident, pinned), table)
            if observed["rss"] > limit:
                raise GuardExceeded("observed_rss_limit")
        proof = _teardown(handle.pid, pinned=pinned, graphroot=graphroot,
                          snapshot=take, sleep=nap, monotonic=mono,
                          command=command, stop=stop, cleanup=cleanup)
        state = {"status": "completed", "plan_sha256": validated["plan_sha256"],
                 "owner": owner, "lease": ident, "exit_code": handle.poll(),
                 "teardown": proof, "enforcement": "userspace_observed",
                 "kernel_enforcement": False}
        lease.release(root, ident, owner=owner, proof=proof)
        return state
    except Exception as exc:
        reason = exc.reason if isinstance(exc, GuardExceeded) else "inspection_unavailable"
        if handle is not None:
            try:
                proof = _teardown(handle.pid, pinned=pinned, graphroot=graphroot,
                                  snapshot=take, sleep=nap, monotonic=mono,
                                  command=command, stop=stop, cleanup=cleanup)
                watchdog.append_group_evidence(
                    root, ident, reason=reason, result="fail_closed", proof=proof)
            except Exception as stop_exc:
                watchdog.blocked_evidence(root, ident, reason,
                                          str(stop_exc)[:200])
        else:
            watchdog.blocked_evidence(root, ident, reason, "pre_spawn_crash")
        if isinstance(exc, GuardExceeded):
            raise
        raise GuardExceeded(reason) from exc
