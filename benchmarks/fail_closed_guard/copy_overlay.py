"""Fail-closed gated launcher for one reviewed binary-only COPY overlay.

The build task is a helper that waits on a private pipe until an exact durable
group bind has been committed, then re-checks the journal and execs the fixed
build command. No generic build mode, no RUN/ADD/network, no inherited temp,
and no successful receipt without real group and owner-scoped storage proof.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from . import (build, disk, heartbeat, lease, orphans, proc, store, watchdog,
               watchdog_contract)
from .errors import GuardExceeded

SCHEMA = "ivanka.copy-overlay-plan.v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{7,64}\Z")
TAG = re.compile(r"ivanka-copy-[0-9a-f]{12,64}\Z")
SOURCE = "ivanka"
DESTINATION = "/usr/local/bin/ivanka"
CONTAINERFILE = "FROM {base}\nCOPY ivanka /usr/local/bin/ivanka\n"
MAX_ARTIFACT = 256 * 1024 * 1024
INTERVAL = 0.5


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


@contextmanager
def shared_lock(root):
    """Hold the actual shared worker lock for the whole admission and watch."""
    path = Path(root) / ".global-worker.lock"
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _under(root, candidate):
    base = Path(root).resolve()
    try:
        target = Path(candidate).resolve()
    except OSError as exc:
        raise GuardExceeded("invalid_plan") from exc
    if target == base or base not in target.parents:
        raise GuardExceeded("invalid_plan")
    return target


def validate_plan(plan, *, expected_base, expected_commit, expected_graphroot,
                  root):
    """Validate one flat artifact and exact Containerfile without TOCTOU."""
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise GuardExceeded("invalid_plan")
    base, commit = plan.get("base_image"), plan.get("source_commit")
    if (not isinstance(base, str) or not DIGEST.fullmatch(base)
            or base != expected_base
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)
            or commit != expected_commit):
        raise GuardExceeded("invalid_plan")
    if (plan.get("source") != SOURCE or plan.get("destination") != DESTINATION
            or plan.get("artifact_mode") != 0o755
            or not isinstance(plan.get("artifact_sha256"), str)
            or not DIGEST.fullmatch(plan["artifact_sha256"])):
        raise GuardExceeded("invalid_plan")
    tag = plan.get("tag")
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise GuardExceeded("invalid_plan")
    if plan.get("graphroot") != str(expected_graphroot):
        raise GuardExceeded("invalid_plan")
    context = _under(root, plan.get("context", ""))
    conf = _under(root, plan.get("storage_conf", ""))
    if context.is_symlink() or not context.is_dir():
        raise GuardExceeded("invalid_plan")
    if conf.is_symlink() or not conf.is_file():
        raise GuardExceeded("invalid_plan")
    entries = sorted(entry.name for entry in os.scandir(context))
    if entries != sorted(("Containerfile", SOURCE)):
        raise GuardExceeded("invalid_plan")
    manifest = context / "Containerfile"
    artifact = context / SOURCE
    if (manifest.is_symlink() or not manifest.is_file()
            or artifact.is_symlink()):
        raise GuardExceeded("invalid_plan")
    if manifest.read_bytes() != CONTAINERFILE.format(base=base).encode():
        raise GuardExceeded("invalid_plan")
    fd = os.open(str(artifact), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_size <= 0 or info.st_size > MAX_ARTIFACT:
            raise GuardExceeded("invalid_plan")
        if info.st_mode & 0o777 != plan["artifact_mode"]:
            raise GuardExceeded("invalid_plan")
        digest = hashlib.sha256()
        remaining = info.st_size
        while remaining:
            chunk = os.read(fd, min(1 << 20, remaining))
            if not chunk:
                raise GuardExceeded("invalid_plan")
            digest.update(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    if digest.hexdigest() != plan["artifact_sha256"]:
        raise GuardExceeded("invalid_plan")
    argv = ["podman", "build", "--network=none", "--pull=never",
            "-f", str(manifest), "-t", tag, str(context)]
    return {"schema": SCHEMA, "base_image": base, "source_commit": commit,
            "context": str(context), "containerfile": str(manifest),
            "source": SOURCE, "destination": DESTINATION,
            "artifact_sha256": plan["artifact_sha256"],
            "artifact_mode": plan["artifact_mode"],
            "storage_conf": str(conf), "graphroot": str(expected_graphroot),
            "tag": tag, "argv": argv, "plan_sha256": plan_digest(plan)}


def helper_argv(root, ident, graphroot, deadline, read_fd, command):
    return [sys.executable, "-m", "fail_closed_guard.copy_overlay_helper",
            "--read-fd", str(read_fd), "--root", str(root),
            "--ident", str(ident), "--graphroot", str(graphroot),
            "--deadline", str(deadline), "--argv"] + list(command)


def default_spawn(root, argv, env, pass_fds, log):
    with Path(log).open("xb") as output:
        return subprocess.Popen(
            argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
            pass_fds=tuple(pass_fds))


def _owned(bound):
    def verify(_pgid, table):
        return watchdog.group_still_owned(bound, table)

    def absent(_pgid, table):
        return watchdog.group_absent(bound, table)

    return verify, absent


def _teardown(bound, *, pinned, graphroot, snapshot, sleep, monotonic,
              command, baseline, expected_name, stop=None, cleanup=None):
    verify, absent = _owned(bound)
    pgid = bound["pgid"]
    terminate = stop if stop is not None else (
        lambda value: build.stop_group_by_id(value, snapshot=snapshot,
                                              sleep=sleep, clock=monotonic,
                                              verify=verify, absent=absent))
    reclaim = cleanup if cleanup is not None else (
        lambda: orphans.reclaim_owned(pinned, graphroot, baseline,
                                      expected_name=expected_name,
                                      command_fn=command))
    proof = terminate(pgid)
    proof["orphan_cleanup"] = reclaim()
    return proof


def _receipt(path, state):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(state, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(root, plan, *, expected_base, expected_commit, graphroot, env=None,
        reserve_bytes=1024**3, wall_seconds=watchdog.DEFAULT_WALL_SECONDS,
        rss_limit=watchdog.RSS_LIMIT, snapshot=None, command=None, usage=None,
        spawn=None, stop=None, cleanup=None, permission=None, wall=None,
        monotonic=None, sleep=None):
    """Admit, gate, observe and prove teardown of one COPY-only overlay build."""
    now = wall if wall is not None else time.time
    mono = monotonic if monotonic is not None else time.monotonic
    nap = sleep if sleep is not None else time.sleep
    take = snapshot if snapshot is not None else proc.snapshot
    command = command or orphans.command
    root = Path(root)
    with shared_lock(root):
        validated = validate_plan(
            plan, expected_base=expected_base, expected_commit=expected_commit,
            expected_graphroot=graphroot, root=root)
        pinned = store.pin_env(dict(env if env is not None else os.environ),
                               storage_conf=validated["storage_conf"])
        store.verify_namespace(pinned, graphroot, command=command)
        watchdog_contract.require_supported_mode("copy_overlay")
        alive = heartbeat.alive_path(root)
        watchdog_contract.require_watchdog_readiness(alive, graphroot=graphroot,
                                                     wall=now, snapshot=take)
        lease.require_clear(root, pinned, watchdog_path=alive,
                            graphroot=graphroot, snapshot=take, wall=now,
                            command=command)
        disk.check_reserve(root, reserve_bytes, usage=usage)
        baseline = orphans.capture_baseline(pinned, graphroot,
                                            command_fn=command)
        ident = "copy-" + validated["plan_sha256"][:16]
        owner = ident
        lease.acquire(root, ident, "copy_overlay", owner=owner)
        start = lease.acquisition_start(root, ident)
        deadline = start + min(wall_seconds, watchdog.DEFAULT_WALL_SECONDS)
        limit = min(rss_limit, watchdog.RSS_LIMIT)
        temp = Path(tempfile.mkdtemp(prefix="copy-", dir=str(root)))
        job_env = {key: value for key, value in pinned.items()
                   if key not in ("TMPDIR", "TMP", "TEMP")}
        job_env.update({"TMPDIR": str(temp), "TMP": str(temp),
                        "TEMP": str(temp)})
        emitter = heartbeat.Emitter(root, ident)
        emitter.before_spawn()
        log = temp / "build.log"
        read_fd, write_fd = os.pipe()
        handle = None
        state = {"tool": "copy_overlay", "lease": ident, "owner": owner,
                 "plan_sha256": validated["plan_sha256"],
                 "status": "unknown", "exit_code": None, "peak_rss": None,
                 "enforcement": "userspace_observed", "kernel_enforcement": False}
        try:
            gate = helper_argv(root, ident, graphroot, deadline, read_fd,
                               validated["argv"])
            maker = spawn or (lambda argv, env_value, pass_fds:
                              default_spawn(root, argv, env_value, pass_fds, log))
            handle = maker(gate, job_env, (read_fd,))
            os.close(read_fd)
            read_fd = None
            table = take()
            record = table.get(handle.pid)
            if record is None or any(record.get(key) is None for key in
                                     ("starttime", "pid_ns")):
                raise GuardExceeded("binding_unavailable")
            stable = [record["starttime"], record["pid_ns"]]
            if record.get("pgid") != handle.pid:
                raise GuardExceeded("identity_lost")
            lease.bind_group(root, ident, handle.pid, handle.pid, stable,
                             owner=owner, plan_sha256=validated["plan_sha256"],
                             graphroot=graphroot, helper=True)
            bound = watchdog.bound_from_lease(root, ident, pinned)
            observed = watchdog.verify_group_bound(bound, table)
            state["peak_rss"] = observed["rss"]
            if observed["rss"] > limit:
                raise GuardExceeded("observed_rss_limit")
            # Permission is only written after the exact durable bind exists.
            (permission or os.write)(write_fd, b"G")
            os.close(write_fd)
            write_fd = None
            while handle.poll() is None:
                if now() >= deadline:
                    raise GuardExceeded("wall_limit")
                disk.check_reserve(root, reserve_bytes, usage=usage)
                emitter.refresh()
                nap(INTERVAL)
                table = take()
                bound = watchdog.bound_from_lease(root, ident, pinned)
                observed = watchdog.verify_group_bound(bound, table)
                state["peak_rss"] = max(state["peak_rss"] or 0,
                                        observed["rss"])
                if observed["rss"] > limit:
                    raise GuardExceeded("observed_rss_limit")
            bound = watchdog.bound_from_lease(root, ident, pinned)
            proof = _teardown(
                bound, pinned=pinned, graphroot=graphroot, snapshot=take,
                sleep=nap, monotonic=mono, command=command, baseline=baseline,
                expected_name=ident + "-working-container", stop=stop,
                cleanup=cleanup)
            state.update({"status": "completed", "exit_code": handle.poll(),
                          "teardown": proof,
                          "orphan_baseline_ids": sorted(baseline)})
            lease.release(root, ident, owner=owner, proof=proof)
        except Exception as exc:
            reason = exc.reason if isinstance(exc, GuardExceeded) else "inspection_unavailable"
            state.update({"status": "failed", "reason": reason,
                          "lease_state": "active_unreleased"})
            if handle is not None:
                try:
                    bound = watchdog.bound_from_lease(root, ident, pinned)
                    if bound.get("state") == "bound_group":
                        proof = _teardown(
                            bound, pinned=pinned, graphroot=graphroot,
                            snapshot=take, sleep=nap, monotonic=mono,
                            command=command, baseline=baseline,
                            expected_name=ident + "-working-container",
                            stop=stop, cleanup=cleanup)
                        watchdog.append_group_evidence(
                            root, ident, reason=reason, result="fail_closed",
                            proof=proof)
                    else:
                        watchdog.blocked_evidence(
                            root, ident, reason, "no_exact_group_bound")
                except Exception as stop_exc:
                    watchdog.blocked_evidence(root, ident, reason,
                                              str(stop_exc)[:200])
            else:
                watchdog.blocked_evidence(root, ident, reason, "pre_bind_crash")
            _receipt(log.parent / "result.json", state)
            if isinstance(exc, GuardExceeded):
                raise
            raise GuardExceeded(reason) from exc
        finally:
            for descriptor in (read_fd, write_fd):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
        _receipt(log.parent / "result.json", state)
        return state
