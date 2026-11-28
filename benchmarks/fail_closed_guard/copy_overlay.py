"""Fail-closed gated launcher for one reviewed binary-only COPY overlay.

The build task is a helper that waits on a private pipe until an exact durable
group bind has been committed, then re-checks the journal and execs the fixed
build command. No generic build mode, no RUN/ADD/network, no inherited temp,
and no successful receipt without real group and owner-scoped storage proof.
"""
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from . import (build, disk, heartbeat, lease, orphans, p1_harness, proc,
               store, watchdog, watchdog_contract)
from .errors import GuardExceeded

SCHEMA = "ivanka.copy-overlay-plan.v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{7,64}\Z")
TAG = re.compile(r"ivanka-copy-[0-9a-f]{12,64}\Z")
SOURCE = "ivanka"
DESTINATION = "/usr/local/bin/ivanka"
CONTAINERFILE = "FROM {base}\nCOPY ivanka /usr/local/bin/ivanka\n"
MAX_ARTIFACT = 256 * 1024 * 1024
# Binding to the one shared PX root also binds to its shared worker lock.
PX_ROOT = "/workspace/ivanka-exploratory-ten-20261121"
MIN_FREE_BYTES = 34_359_738_368
INTERVAL = 0.5


def require_px_root(root):
    """Only the shared PX project root may host a bounded overlay build."""
    if Path(root).resolve() != Path(PX_ROOT).resolve():
        raise GuardExceeded("wrong_project_root")


def check_disk_floor(root, reserve_bytes, usage=None):
    """Hard 32 GiB free floor plus the per-job reservation, in one reading."""
    space = (usage or (lambda path: shutil.disk_usage(str(path))))(str(root))
    free = getattr(space, "free", None)
    if (not isinstance(free, (int, float)) or not math.isfinite(free)
            or free - reserve_bytes < MIN_FREE_BYTES):
        raise GuardExceeded("reserve_shortfall")
    disk.check_reserve(root, reserve_bytes, usage=lambda _path: space)
    return free


def check_stop(root, owner):
    """Reuse the P1 STOP contract: it must exist and name this exact owner."""
    sentinel = Path(root) / "STOP"
    return p1_harness.require_owned_stop(sentinel, owner)


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def normalize_digest(value):
    """Accept Podman's ``sha256:`` form and compare only the exact bare digest."""
    if isinstance(value, str):
        bare = value.strip().removeprefix("sha256:").lower()
        if DIGEST.fullmatch(bare):
            return bare
    raise GuardExceeded("invalid_plan")


def verify_sealed(context, *, base, artifact_sha256, artifact_mode):
    """Re-prove an immutable private context immediately before exec."""
    directory = Path(context)
    if (directory.is_symlink() or not directory.is_dir()
            or stat.S_IMODE(directory.stat().st_mode) != 0o500):
        raise GuardExceeded("context_unsealed")
    entries = sorted(entry.name for entry in os.scandir(directory))
    if entries != sorted(("Containerfile", SOURCE)):
        raise GuardExceeded("context_unsealed")
    manifest, artifact = directory / "Containerfile", directory / SOURCE
    if (manifest.is_symlink() or artifact.is_symlink()
            or manifest.read_bytes() != CONTAINERFILE.format(base=base).encode()
            or stat.S_IMODE(manifest.stat().st_mode) != 0o400):
        raise GuardExceeded("context_unsealed")
    fd = os.open(str(artifact), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != artifact_mode:
            raise GuardExceeded("context_unsealed")
        digest = hashlib.sha256()
        remaining = info.st_size
        while remaining:
            chunk = os.read(fd, min(1 << 20, remaining))
            if not chunk:
                raise GuardExceeded("context_unsealed")
            digest.update(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    if digest.hexdigest() != artifact_sha256:
        raise GuardExceeded("context_unsealed")
    return str(directory)


def seal_context(temp, validated):
    """Copy the reviewed plan into a private, then read-only, build context."""
    sealed = Path(temp) / "context"
    sealed.mkdir(mode=0o700)
    source_dir = Path(validated["context"])
    shutil.copyfile(source_dir / "Containerfile", sealed / "Containerfile")
    shutil.copyfile(source_dir / SOURCE, sealed / SOURCE)
    os.chmod(sealed / "Containerfile", 0o400)
    os.chmod(sealed / SOURCE, validated["artifact_mode"])
    os.chmod(sealed, 0o500)
    verify_sealed(sealed, base=validated["base_image"],
                  artifact_sha256=validated["artifact_sha256"],
                  artifact_mode=validated["artifact_mode"])
    validated["containerfile"] = str(sealed / "Containerfile")
    validated["context"] = str(sealed)
    iidfile = Path(temp) / "image.iid"
    labels = [
        "org.ottojung.ivanka.source-commit=" + validated["source_commit"],
        "org.ottojung.micall.frozen-image-id=" + validated["base_image"],
        "org.ottojung.ivanka.binary-sha256=" + validated["artifact_sha256"],
        "org.ottojung.ivanka.frozen-manifest-sha256="
        + validated["frozen_manifest_sha256"],
        "org.ottojung.ivanka.pilot-role=" + validated["pilot_role"],
    ]
    argv = ["podman", "build", "--network=none", "--pull=never"]
    # A pinned plan boolean may disable caches. The guard constructs this flag
    # itself; a plan can never inject an arbitrary command or flag.
    if validated.get("no_cache"):
        argv.append("--no-cache")
    argv.extend(["--iidfile", str(iidfile)])
    for label in labels:
        argv.extend(["--label", label])
    argv.extend(["-f", validated["containerfile"], "-t", validated["tag"],
                 str(sealed)])
    validated["argv"] = argv
    validated["iidfile"] = str(iidfile)
    validated["labels"] = labels
    return str(sealed)


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
    base = normalize_digest(plan.get("base_image"))
    if (base != normalize_digest(expected_base)
            or not isinstance(plan.get("source_commit"), str)
            or not COMMIT.fullmatch(plan["source_commit"])
            or plan["source_commit"] != expected_commit):
        raise GuardExceeded("invalid_plan")
    commit = plan["source_commit"]
    artifact_sha = normalize_digest(plan.get("artifact_sha256"))
    if (plan.get("source") != SOURCE or plan.get("destination") != DESTINATION
            or plan.get("artifact_mode") != 0o755):
        raise GuardExceeded("invalid_plan")
    frozen_manifest = normalize_digest(plan.get("frozen_manifest_sha256"))
    pilot_role = plan.get("pilot_role")
    if not isinstance(pilot_role, str) or not pilot_role:
        raise GuardExceeded("invalid_plan")
    tag = plan.get("tag")
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise GuardExceeded("invalid_plan")
    code_root = Path(plan.get("code_root", ""))
    helper = code_root / "benchmarks/fail_closed_guard/copy_overlay_helper.py"
    if (code_root.is_symlink() or not code_root.is_dir()
            or helper.is_symlink() or not helper.is_file()
            or hashlib.sha256(helper.read_bytes()).hexdigest()
            != normalize_digest(plan.get("code_sha256"))):
        raise GuardExceeded("invalid_plan")
    if plan.get("graphroot") != str(expected_graphroot):
        raise GuardExceeded("invalid_plan")
    raw_layers = plan.get("base_layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise GuardExceeded("invalid_plan")
    layers = [normalize_digest(item) for item in raw_layers]
    conf_sha = normalize_digest(plan.get("storage_conf_sha256"))
    context = _under(root, plan.get("context", ""))
    conf = _under(root, plan.get("storage_conf", ""))
    if context.is_symlink() or not context.is_dir():
        raise GuardExceeded("invalid_plan")
    if conf.is_symlink() or not conf.is_file():
        raise GuardExceeded("invalid_plan")
    conf_fd = os.open(str(conf), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        conf_digest = hashlib.sha256()
        while True:
            chunk = os.read(conf_fd, 1 << 20)
            if not chunk:
                break
            conf_digest.update(chunk)
    finally:
        os.close(conf_fd)
    if conf_digest.hexdigest() != conf_sha:
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
    if digest.hexdigest() != artifact_sha:
        raise GuardExceeded("invalid_plan")
    no_cache = plan.get("no_cache", False)
    if not isinstance(no_cache, bool):
        raise GuardExceeded("invalid_plan")
    argv = ["podman", "build", "--network=none", "--pull=never"]
    if no_cache:
        argv.append("--no-cache")
    argv.extend(["-f", str(manifest), "-t", tag, str(context)])
    return {"schema": SCHEMA, "base_image": base, "source_commit": commit,
            "context": str(context), "containerfile": str(manifest),
            "source": SOURCE, "destination": DESTINATION,
            "artifact_sha256": artifact_sha,
            "artifact_mode": plan["artifact_mode"],
            "frozen_manifest_sha256": frozen_manifest,
            "pilot_role": pilot_role, "code_root": str(code_root),
            "inherited_labels": dict(plan.get("inherited_labels") or {}),
            "storage_conf": str(conf), "graphroot": str(expected_graphroot),
            "storage_conf_sha256": conf_sha,
            "base_layers": list(layers), "no_cache": no_cache,
            "tag": tag, "argv": argv, "plan_sha256": plan_digest(plan)}


def helper_argv(root, ident, graphroot, deadline, deadline_mono, read_fd,
                command, *, context, base, artifact_sha256, artifact_mode):
    return [sys.executable, "-m", "fail_closed_guard.copy_overlay_helper",
            "--read-fd", str(read_fd), "--root", str(root),
            "--ident", str(ident), "--graphroot", str(graphroot),
            "--deadline", str(deadline), "--deadline-monotonic",
            str(deadline_mono), "--context", str(context),
            "--base", str(base), "--artifact-sha256", str(artifact_sha256),
            "--artifact-mode", str(artifact_mode), "--argv"] + list(command)


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
        return watchdog.group_absence_proven(bound, table)

    return verify, absent


def _teardown(bound, *, pinned, graphroot, snapshot, sleep, monotonic,
              command, baseline, stop=None, cleanup=None):
    verify, absent = watchdog.group_callbacks(bound)
    pgid = bound["pgid"]
    terminate = stop if stop is not None else (
        lambda value: build.stop_group_by_id(value, snapshot=snapshot,
                                              sleep=sleep, clock=monotonic,
                                              verify=verify, absent=absent))
    reclaim = cleanup if cleanup is not None else (
        lambda: orphans.reclaim_owned(
            pinned, graphroot, baseline,
            expected_base=bound.get("base_image"),
            base_layers=bound.get("base_layers") or [], command_fn=command))
    proof = terminate(pgid)
    proof["orphan_cleanup"] = reclaim()
    return proof


IMAGE_FORMAT = "{{.Id}}|{{json .Config.Labels}}|{{json .RootFS.Layers}}"


def verify_image_receipt(validated, env, command_fn=None):
    """Bind the built image to exact digest, reviewed labels and one new layer."""
    run = command_fn or orphans.command
    identifier = normalize_digest(
        Path(validated["iidfile"]).read_text().strip())
    fields = run(["podman", "image", "inspect", "--format",
                  IMAGE_FORMAT, identifier], env).split("|")
    if len(fields) != 3:
        raise GuardExceeded("image_receipt_invalid")
    try:
        labels = json.loads(fields[1])
        layers = json.loads(fields[2])
    except ValueError as exc:
        raise GuardExceeded("image_receipt_invalid") from exc
    expected = dict(item.split("=", 1) for item in validated["labels"])
    expected.update(validated.get("inherited_labels") or {})
    normalized_layers = [normalize_digest(item) for item in layers] \
        if isinstance(layers, list) else []
    if (normalize_digest(fields[0].strip()) != identifier
            or not isinstance(labels, dict)
            or any(labels.get(key) != value for key, value in expected.items())
            or normalized_layers[:len(validated["base_layers"])]
            != validated["base_layers"]
            or len(normalized_layers) != len(validated["base_layers"]) + 1):
        raise GuardExceeded("image_receipt_invalid")
    return {"image": identifier, "labels": {key: labels[key]
                                            for key in expected},
            "base_layers": validated["base_layers"],
            "layers": normalized_layers,
            "one_layer_overlay": True, "kernel_enforcement": False}


def _downgrade(root, ident, state):
    """A watchdog fail-closed teardown can never leave a finished receipt."""
    try:
        return watchdog_contract.downgrade_on_watchdog_teardown(
            root, ident, state)
    except GuardExceeded:
        updated = dict(state)
        updated["status"] = "failed"
        updated["reason"] = "watchdog_evidence_unreadable"
        return updated


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
        require_px_root(root)
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
        check_disk_floor(root, reserve_bytes, usage)
        ident = "copy-" + validated["plan_sha256"][:16]
        check_stop(root, ident)
        baseline = orphans.capture_baseline(pinned, graphroot,
                                            command_fn=command)
        owner = ident
        lease.acquire(root, ident, "copy_overlay", owner=owner)
        start = lease.acquisition_start(root, ident)
        budget = min(wall_seconds, watchdog.DEFAULT_WALL_SECONDS)
        deadline = start + budget
        deadline_mono = mono() + budget
        limit = min(rss_limit, watchdog.RSS_LIMIT)
        temp = Path(tempfile.mkdtemp(prefix="copy-", dir=str(root)))
        # No inherited host variables: only the pinned store and known PATH.
        job_env = {key: pinned[key] for key in ("PATH", "HOME",
                                                "CONTAINERS_STORAGE_CONF")
                   if key in pinned}
        job_env.update({"TMPDIR": str(temp), "TMP": str(temp),
                        "TEMP": str(temp)})
        code = Path(validated["code_root"])
        job_env["PYTHONPATH"] = os.pathsep.join(
            (str(code / "benchmarks"), str(code)))
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
            sealed = seal_context(temp, validated)
            gate = helper_argv(
                root, ident, graphroot, deadline, deadline_mono, read_fd,
                validated["argv"],
                context=sealed, base=validated["base_image"],
                artifact_sha256=validated["artifact_sha256"],
                artifact_mode=validated["artifact_mode"])
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
            lease.bind_group(
                root, ident, handle.pid, handle.pid, stable, owner=owner,
                plan_sha256=validated["plan_sha256"], graphroot=graphroot,
                helper=True, baseline_ids=sorted(baseline),
                base_image=validated["base_image"],
                base_layers=validated["base_layers"],
                storage_conf_sha256=validated["storage_conf_sha256"])
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
                if now() >= deadline or mono() >= deadline_mono:
                    raise GuardExceeded("wall_limit")
                check_disk_floor(root, reserve_bytes, usage)
                emitter.refresh()
                nap(INTERVAL)
                table = take()
                bound = watchdog.bound_from_lease(root, ident, pinned)
                observed = watchdog.verify_group_bound(bound, table)
                state["peak_rss"] = max(state["peak_rss"] or 0,
                                        observed["rss"])
                if observed["rss"] > limit:
                    raise GuardExceeded("observed_rss_limit")
            if now() >= deadline or mono() >= deadline_mono:
                raise GuardExceeded("wall_limit")
            image = verify_image_receipt(validated, job_env, command)
            if now() >= deadline or mono() >= deadline_mono:
                raise GuardExceeded("wall_limit")
            bound = watchdog.bound_from_lease(root, ident, pinned)
            proof = _teardown(
                bound, pinned=pinned, graphroot=graphroot, snapshot=take,
                sleep=nap, monotonic=mono, command=command, baseline=baseline,
                stop=stop, cleanup=cleanup)
            exit_code = handle.poll()
            expired = now() >= deadline or mono() >= deadline_mono
            if expired:
                # The budget ended during inspect/teardown: keep the proof but
                # never publish a completed result after the deadline.
                watchdog.append_group_evidence(
                    root, ident, reason="wall_limit", result="fail_closed",
                    proof=proof)
            reason_value = ("wall_limit" if expired else
                            None if exit_code == 0 else "build_exit_nonzero")
            state.update({
                "status": "completed" if reason_value is None else "failed",
                "reason": reason_value, "exit_code": exit_code,
                "teardown": proof, "image_receipt": image,
                "orphan_baseline_ids": sorted(baseline)})
            lease.release(root, ident, owner=owner, proof=proof)
            if expired:
                state = _downgrade(root, ident, state)
                _receipt(log.parent / "result.json", state)
                return state
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
            _receipt(log.parent / "result.json", _downgrade(root, ident, state))
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
        state = _downgrade(root, ident, state)
        _receipt(log.parent / "result.json", state)
        return state
