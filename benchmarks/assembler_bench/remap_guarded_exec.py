"""Real guarded execution for remap diagnostic pilots.

This is the non-mock execution path used by
``remap_pilot_controller.execute_case``. Importing it starts nothing. A case
is executed only through :func:`run_guarded_case`, which delegates the whole
pre-spawn/lifecycle to the proven shared ``p1_harness.run_prospective`` guard
(exclusive lock, owner-bound STOP sentinel, lease, watchdog readiness,
independent disk reserve, exact-CID binding, durable heartbeat refresh,
strict teardown proof) and never invents an ad-hoc launcher contract.

No frozen source, image, result, registry or qualification input is changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from fail_closed_guard import disk, p1_harness
from fail_closed_guard import proc
# Re-exported guard modules so integration tests can inject only low-level
# seams (CID inspect, /proc snapshot, podman CLI result, disk usage).
from fail_closed_guard import (binding, heartbeat, lease, natural_exit, stop,  # noqa: F401
                               teardown)
from fail_closed_guard.errors import GuardExceeded

from . import guarded_canary_launcher as launcher
from .exploratory_runtime import monitor, pilot
from .px_ram_semantics import (
    METHOD_KEY,
    SCOPE_KEY,
    VERSION_KEY,
)

# Independent original read-pair attestation produced by the operator-side
# readback (not derived by this controller, the runner rows or a result file).
ORIGINAL_MANIFEST = Path(
    "/workspace/ivanka-storage-recovery-20261126/"
    "remap-input-attestation-20261126/readback.json")
ORIGINAL_MANIFEST_SHA256 = (
    "01c59cfad729f256c65cd49f1f0c4ef2cc0d75cbd357cbceeea35d075e2901df")
MANIFEST_SCHEMA = "ivanka.remap.read-pair-preflight.v1"
EXPECTED_COUNTS = {"physical": 198, "synthetic": 464}
COHORT_MAP = {"physical": "real", "synthetic": "synthetic"}
CANONICAL_ALIAS = re.compile(r"^PX-([RH])([0-9]{3})$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Shared dedicated guard root/store. No new store, guard or privilege is added.
GUARD_ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
STORAGE_CONF = GUARD_ROOT / "storage.conf"
WORKSPACE = Path("/workspace")
LOCK_PATH = GUARD_ROOT / ".global-worker.lock"
STOP_PATH = GUARD_ROOT / ".remap-pilot.STOP"
LOG_NAMES = ("launcher.stdout.log", "launcher.stderr.log")
RESERVE_BYTES = p1_harness.DEFAULT_RESERVE_BYTES

EXECUTION_SCHEMA = "ivanka.remap.guarded-execution.v1"
BINDING_SCHEMA = "ivanka.remap.original-input-binding.v1"


def _sha256_file(path: os.PathLike[str] | str) -> str:
    return launcher.sha256_file(path)


def load_original_input_manifest(path=ORIGINAL_MANIFEST, *,
                                 expected_sha=ORIGINAL_MANIFEST_SHA256) -> dict:
    """Verify the independently attested original 198+464 read-pair manifest.

    ``expected_sha`` is injectable ONLY for hermetic synthetic fixtures in
    source tests. Production callers keep the pinned private-manifest digest;
    no fixture or private manifest is ever published in the repository.
    """
    source = Path(path)
    if not source.is_file() or _sha256_file(source) != expected_sha:
        raise ValueError("original remap input manifest digest changed")
    manifest = json.loads(source.read_bytes())
    if (manifest.get("schema") != MANIFEST_SCHEMA
            or manifest.get("truth_opened") is not False
            or manifest.get("errors")
            or manifest.get("counts") != EXPECTED_COUNTS):
        raise ValueError("original remap input manifest is not clean")
    for key in ("physical_manifest_sha256", "synthetic_cohort_sha256"):
        if not HEX64.fullmatch(str(manifest.get(key) or "")):
            raise ValueError("original cohort pin is missing")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != sum(EXPECTED_COUNTS.values()):
        raise ValueError("original manifest case count changed")
    index = {}
    for case in cases:
        alias = case.get("alias")
        match = CANONICAL_ALIAS.fullmatch(str(alias or ""))
        if not match or case.get("cohort") not in COHORT_MAP:
            raise ValueError("original manifest alias/cohort is not canonical")
        if COHORT_MAP[case["cohort"]] != ("real" if match.group(1) == "R" else "synthetic"):
            raise ValueError("original manifest cohort prefix mismatch")
        reads = case.get("reads") or {}
        digests = {}
        for mate in ("R1", "R2"):
            value = reads.get(mate) or {}
            digest = value.get("sha256")
            if (value.get("source_verified") is not True
                    or not HEX64.fullmatch(str(digest or ""))):
                raise ValueError("original manifest read is not source-verified")
            digests[mate] = digest
        canonical = alias[3:]
        if canonical in index:
            raise ValueError("duplicate original manifest alias")
        index[canonical] = {
            "alias": canonical,
            "cohort": COHORT_MAP[case["cohort"]],
            "read_sha256": digests,
            "source_verified": True,
        }
    return {
        "schema": BINDING_SCHEMA,
        "manifest_path": str(source),
        "manifest_sha256": expected_sha,
        "physical_manifest_sha256": manifest["physical_manifest_sha256"],
        "synthetic_cohort_sha256": manifest["synthetic_cohort_sha256"],
        "truth_opened": False,
        "cases": [index[key] for key in sorted(index)],
    }


def bind_plan_to_original_manifest(plan: dict, manifest: dict) -> dict:
    """Prove the plan uses attested original reads from the 662-case manifest."""
    if not isinstance(manifest, dict) or manifest.get("schema") != BINDING_SCHEMA:
        raise ValueError("no verified original input manifest")
    alias, cohort = plan.get("alias"), plan.get("cohort")
    if cohort not in ("real", "synthetic") or not re.fullmatch(r"[RH][0-9]{3}", str(alias or "")):
        raise ValueError("plan alias/cohort is not canonical")
    expected = next((c for c in manifest["cases"] if c["alias"] == alias), None)
    if expected is None or expected["cohort"] != cohort:
        raise ValueError("plan case is absent from original input manifest")
    reads = (plan.get("inputs") or {}).get("read_sha256") or {}
    if reads != expected["read_sha256"]:
        raise ValueError("plan reads differ from original attested input manifest")
    return {
        "schema": BINDING_SCHEMA,
        "alias": alias,
        "cohort": cohort,
        "original_manifest_sha256": manifest["manifest_sha256"],
        "physical_manifest_sha256": manifest["physical_manifest_sha256"],
        "synthetic_cohort_sha256": manifest["synthetic_cohort_sha256"],
        "read_sha256": dict(reads),
        "source_verified": True,
    }


def safe_guard_env(root, temp_dir):
    """Explicit environment; ambient container selectors are never trusted."""
    base = Path(root).resolve()
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CONTAINERS_STORAGE_CONF": str(base / "storage.conf"),
        "TMPDIR": str(temp_dir),
        "TMP": str(temp_dir),
        "TEMP": str(temp_dir),
    }
    for key in list(env):
        if key not in ("PATH", "CONTAINERS_STORAGE_CONF", "TMPDIR", "TMP", "TEMP"):
            env.pop(key)
    return env


def pinned_plan_argv(plan: dict, cidfile) -> list[str]:
    """Rebind the plan's exact command to the lease-pinned cidfile only."""
    argv = list(plan.get("argv") or [])
    if "--cidfile" not in argv:
        raise ValueError("plan argv has no cidfile")
    index = argv.index("--cidfile")
    if index + 1 >= len(argv):
        raise ValueError("plan argv cidfile is empty")
    argv[index + 1] = str(cidfile)
    mounts = [argv[i + 1] for i in range(len(argv) - 1) if argv[i] == "-v"]
    allowed = frozenset(v for v in argv if v not in mounts) | frozenset({"podman"})
    sources = frozenset(m.rsplit(":", 2)[0] for m in mounts)
    reads = tuple((plan.get("inputs") or {}).get("read_basenames") or [])
    if len(reads) != 2:
        raise ValueError("plan lacks attested read basenames")
    image_id = (plan.get("image") or {}).get("id")
    launcher.assert_reference_blind(
        argv, allowed_values=allowed, expected_sources=sources,
        denovo=False, reads=reads, image_id=image_id)
    return argv


def _unmount_proof(root, env, cid, teardown_proof) -> dict:
    """Require exact-CID absence proof before any posthoc scoring can run."""
    proof = pilot.prove_pilot_absent(root, env, cid, proof=teardown_proof)
    if proof.get("fresh_absence_check") is not True:
        raise ValueError("unmount proof lacks fresh absence check")
    return dict(proof, unmount_verified=True)


def _guard_receipt(result, *, plan, samples, unmount_proof) -> dict:
    cid = result.get("cid")
    if not isinstance(cid, str) or not HEX64.fullmatch(cid):
        raise ValueError("guard result has no exact bound CID")
    bounds = plan.get("guard") or {}
    return {
        "schema": EXECUTION_SCHEMA,
        "bound_cid": cid,
        "rss_limit_bytes": bounds.get("rss_limit_bytes"),
        "wall_seconds": bounds.get("wall_seconds"),
        "cpu_allocation": bounds.get("cpu_allocation"),
        "kernel_enforcement": False,
        "samples": samples,
        "observation_ended": isinstance(result.get("natural_exit"), dict)
        or isinstance(result.get("teardown"), dict),
        "teardown": result.get("teardown"),
        "unmount_proof": unmount_proof,
    }


def run_guarded_case(plan: dict, original_manifest: dict, *, output_dir, attempt_dir,
                     owner=None, stop_path=None, watchdog_ready=None,
                     watchdog_path=None, watchdog_graphroot=None,
                     spawn=None, env=None, guard_root=GUARD_ROOT,
                     disk_path=WORKSPACE, clock=None,
                     sleep=None, disk_usage=None, harness=None):
    """Execute ONE case via the proven shared prospective guard.

    ``owner`` is the operator slot identity and ``stop_path`` the owner-bound
    STOP sentinel; neither has a permissive default. ``watchdog_ready`` is the
    operator-supplied readiness checker. Missing gates fail closed before any
    lock, lease or spawn. ``spawn`` is the only container-seam injection;
    production uses :func:`_spawn_plan`, tests inject a low-level double.

    All guard functions (lock, STOP, lease, watchdog, disk reserve, exact-CID
    binding, heartbeat refresh, watcher, exact-CID teardown) are the real
    shared implementations from ``p1_harness``/``fail_closed_guard``.
    """
    harness = harness or p1_harness
    guard_root = Path(guard_root).resolve()
    output_dir, attempt_dir = Path(output_dir), Path(attempt_dir)
    state = {"schema": EXECUTION_SCHEMA, "status": "unknown",
             "bound_cid": None, "unmount_verified": False,
             "unmount_proof": None, "guard_receipt": None,
             "failure_reason": None}

    binding_record = bind_plan_to_original_manifest(plan, original_manifest)
    state["original_input_binding"] = binding_record
    if not owner or not stop_path:
        state.update(status="failed", failure_reason="operator_slot_not_armed")
        return state
    if watchdog_ready is None and not (watchdog_path and watchdog_graphroot):
        # Either an operator-supplied readiness checker or a real readiness
        # record bound to the exact graphroot is mandatory. No ambient watchdog.
        state.update(status="failed", failure_reason="watchdog_not_bound")
        return state
    # Independent reserve check also happens inside the harness under the
    # lock and on every watcher sample; this early check avoids any setup.
    try:
        free = disk.check_reserve(str(disk_path), RESERVE_BYTES, usage=disk_usage)
    except GuardExceeded as exc:
        state.update(status="failed", failure_reason="reserve_shortfall")
        state["capacity"] = {"admitted": False, "reason": exc.reason, "detail": str(exc)}
        return state
    state["capacity"] = {"admitted": True, "free_bytes": int(free),
                         "reserved_bytes": RESERVE_BYTES}

    attempt_dir.mkdir(parents=True, exist_ok=True)
    launcher.setup_bad_cycles(attempt_dir)
    launcher.write_receipt(
        attempt_dir, case=str(plan.get("alias")),
        attempt_id=str(plan.get("attempt_id")), argv=list(plan["argv"]),
        status="attempted")

    if guard_root == GUARD_ROOT.resolve():
        # Production store binding: the frozen plan's explicit podman root and
        # runroot must be the ones named by the pinned storage.conf. No ambient
        # selector and no foreign store may satisfy the guard.
        import configparser
        parser = configparser.ConfigParser()
        if not parser.read(guard_root / "storage.conf"):
            raise ValueError("pinned storage.conf is missing")
        section = {key: value.strip("\"'") for key, value
                   in parser["storage"].items()}
        argv = list(plan.get("argv") or [])
        for flag, key in (("--root", "graphroot"), ("--runroot", "runroot")):
            if flag not in argv or argv[argv.index(flag) + 1] != section.get(key):
                raise ValueError(f"plan argv {flag} does not match pinned storage.conf")

    guard_env = env or safe_guard_env(guard_root, attempt_dir)
    if guard_env.get("CONTAINERS_STORAGE_CONF") != str(guard_root / "storage.conf"):
        raise ValueError("guard environment storage selector is not pinned")
    for key in guard_env:
        if key.startswith(("CONTAINERS_", "PODMAN_", "DOCKER_")) \
                and key != "CONTAINERS_STORAGE_CONF":
            raise ValueError("ambient container selector in guard environment")

    stdout = attempt_dir / LOG_NAMES[0]
    stderr = attempt_dir / LOG_NAMES[1]
    holder = {}
    counter = {"samples": 0}

    def checked_ready():
        # Called by the harness on every sample alongside emitter.refresh().
        counter["samples"] += 1
        return watchdog_ready()

    def do_spawn(cidfile, spawn_env):
        actual = spawn or _spawn_plan
        proc = actual(plan, Path(cidfile), spawn_env, stdout, stderr, guard_root)
        holder["proc"] = proc
        return proc

    class LauncherHandle:
        def poll(self):
            return holder["proc"].poll()

    def running():
        proc = holder.get("proc")
        return proc is not None and proc.poll() is None

    outcome = None
    try:
        outcome = harness.run_prospective(
            owner=owner, lease_root=guard_root, stop_path=stop_path,
            disk_path=disk_path, spawn=do_spawn, env=guard_env,
            lock=harness.ExclusiveLock(LOCK_PATH if guard_root == GUARD_ROOT
                                       else guard_root / ".global-worker.lock"),
            watchdog_ready=(checked_ready if watchdog_ready is not None else None),
            watchdog_path=watchdog_path, watchdog_graphroot=watchdog_graphroot,
            disk_reserve_bytes=RESERVE_BYTES, disk_usage=disk_usage,
            limit=int(plan["guard"]["rss_limit_bytes"]),
            wall_seconds=int(plan["guard"]["wall_seconds"]),
            running=running,
            measure=lambda: disk.check_reserve(str(disk_path), RESERVE_BYTES,
                                               usage=disk_usage),
            snapshot=proc.snapshot, clock=clock, sleep=sleep,
            attestation={"method": monitor.BOUND_ATTESTATION[METHOD_KEY],
                         "version": monitor.BOUND_ATTESTATION[VERSION_KEY]},
            launcher=LauncherHandle(), interval=0.5)
    except GuardExceeded as exc:
        state.update(status="failed", failure_reason=exc.reason,
                     guard_result=exc.guard_result, teardown=exc.teardown,
                     teardown_error=exc.teardown_error)
    except Exception as exc:
        state.update(status="failed",
                     failure_reason=f"{type(exc).__name__}:{exc}"[:320])

    if outcome is not None:
        result = outcome.get("result") or {}
        state["guard_result"] = result
        state["bound_cid"] = result.get("cid")
        state["harness_outcome"] = outcome.get("status")
        if outcome.get("status") == "completed" and result.get("teardown"):
            try:
                proof = _unmount_proof(guard_root, guard_env, result["cid"],
                                       result["teardown"])
                state["unmount_proof"] = proof
                state["unmount_verified"] = True
                state["guard_receipt"] = _guard_receipt(
                    result, plan=plan, samples=counter["samples"],
                    unmount_proof=proof)
                # Actual field names verified from watch.watch_bound._result.
                state["resource"] = {
                    "peak_rss_bytes": result.get("peak_rss"),
                    "samples": counter["samples"],
                    "observation_ended": state["guard_receipt"]["observation_ended"],
                    "bound_cid": result.get("cid"),
                    "guard_receipt": state["guard_receipt"],
                    METHOD_KEY: result.get("method"),
                    VERSION_KEY: result.get("version"),
                    SCOPE_KEY: result.get("rss_sample_scope"),
                }
                proc_handle = holder.get("proc")
                state["returncode"] = proc_handle.poll() if proc_handle else None
                if state["returncode"] == 0:
                    state["status"] = "finished"
                else:
                    state.update(status="failed",
                                 failure_reason=f"exit_{state['returncode']}")
            except (ValueError, GuardExceeded, OSError) as exc:
                state.update(status="failed",
                             failure_reason=f"unmount_unverified:{exc}"[:320])
        else:
            state.update(status="failed",
                         failure_reason=outcome.get("reason", "guard_fail_closed"))
    if not state["unmount_verified"]:
        # Never leave a live/unproved container owned by a completed receipt.
        state["lease_state"] = "active_unreleased_or_unproven"
        state["status"] = "failed"
    state["log_paths"] = {LOG_NAMES[0]: str(stdout), LOG_NAMES[1]: str(stderr)}
    # A failed pre-bind launch can copy logs before the child has exited and
    # flushed. Prove the exact launcher exited (bounded), then hash the final
    # bytes. Blind sleeps with a live unbound container are never used.
    proc_handle = holder.get("proc")
    if proc_handle is not None and proc_handle.poll() is None:
        waiter = getattr(proc_handle, "wait", None)
        if not callable(waiter):
            state.update(status="failed", failure_reason="launcher_exit_unproven")
        else:
            try:
                waiter(timeout=30)
            except Exception as exc:
                state.update(status="failed",
                             failure_reason="launcher_exit_unproven:" +
                             type(exc).__name__)
    state["launcher_exited"] = (proc_handle is None
                                or proc_handle.poll() is not None)
    if not state["launcher_exited"]:
        failure = str(state.get("failure_reason") or "")
        state["failure_reason"] = (failure + ":launcher_exit_unproven")[:320] \
            if failure else "launcher_exit_unproven"
    log_hashes = {}
    for path in (stdout, stderr):
        if path.is_file():
            log_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    state["log_sha256"] = log_hashes
    return state


def _spawn_plan(plan, cidfile, env, stdout, stderr, guard_root):
    """Real Podman spawn of the exact frozen non-de-novo argv."""
    argv = pinned_plan_argv(plan, cidfile)
    with stdout.open("xb") as out, stderr.open("xb") as err:
        return subprocess.Popen(argv, cwd=str(Path(guard_root).resolve()),
                                env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
