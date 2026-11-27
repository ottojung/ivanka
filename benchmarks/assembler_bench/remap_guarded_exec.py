"""Real guarded execution for remap diagnostic pilots.

This module is the non-mock execution path used by
``remap_pilot_controller.execute_case``. Importing it starts nothing. A case
is executed only through :func:`run_guarded_case`, which re-checks the
reserve, takes the exclusive shared slot, binds the exact issued CID through
the common fail-closed watcher, and returns the real end state and resource
evidence. Posthoc scoring is a separate controller step that requires an
unmount/teardown proof from this module.

No frozen source, image, result, registry or qualification input is changed.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from pathlib import Path

from fail_closed_guard import heartbeat, lease
from fail_closed_guard.errors import GuardExceeded

from . import exploratory_space, guarded_canary_launcher as launcher
from . import remap_runner
from .exploratory_runtime import monitor
from .exploratory_runtime import pilot, terminate
from .px_ram_semantics import (
    COMPARABLE_METHOD,
    COMPARABLE_METHOD_VERSION,
    COMPARABLE_SCOPE,
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

# Shared dedicated guard root/store. No new store, guard or privilege is
# introduced; remap uses the same exclusive slot and exact-CID teardown.
GUARD_ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
STORAGE_CONF = GUARD_ROOT / "storage.conf"
WORKSPACE = Path("/workspace")
LOG_NAMES = ("launcher.stdout.log", "launcher.stderr.log")

EXECUTION_SCHEMA = "ivanka.remap.guarded-execution.v1"
BINDING_SCHEMA = "ivanka.remap.original-input-binding.v1"


def _sha256_file(path: os.PathLike[str] | str) -> str:
    return launcher.sha256_file(path)


def load_original_input_manifest(path=ORIGINAL_MANIFEST) -> dict:
    """Verify the independently attested original 198+464 read-pair manifest."""
    source = Path(path)
    if not source.is_file() or _sha256_file(source) != ORIGINAL_MANIFEST_SHA256:
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
        "manifest_sha256": ORIGINAL_MANIFEST_SHA256,
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


def cidfile_from_argv(argv) -> Path:
    """Read the exact cidfile already pinned in the frozen plan argv."""
    if not isinstance(argv, list) or "--cidfile" not in argv:
        raise ValueError("plan argv has no exact cidfile")
    index = argv.index("--cidfile")
    if index + 1 >= len(argv) or not argv[index + 1]:
        raise ValueError("plan argv cidfile is empty")
    return Path(argv[index + 1])


def _unmount_proof(root, env, cid, teardown) -> dict:
    """Require exact-CID absence proof before any posthoc scoring can run."""
    proof = pilot.prove_pilot_absent(root, env, cid, proof=teardown)
    if proof.get("fresh_absence_check") is not True:
        raise ValueError("unmount proof lacks fresh absence check")
    return dict(proof, unmount_verified=True)


def _guard_receipt(observation, *, plan, samples, unmount_proof) -> dict:
    cid = observation.get("cid")
    if not isinstance(cid, str) or not HEX64.fullmatch(cid):
        raise ValueError("guard observation has no exact bound CID")
    bounds = plan.get("guard") or {}
    return {
        "schema": EXECUTION_SCHEMA,
        "bound_cid": cid,
        "rss_limit_bytes": bounds.get("rss_limit_bytes"),
        "wall_seconds": bounds.get("wall_seconds"),
        "cpu_allocation": bounds.get("cpu_allocation"),
        "kernel_enforcement": False,
        "samples": samples,
        "observation_ended": True,
        "teardown": observation.get("teardown"),
        "unmount_proof": unmount_proof,
    }


def run_guarded_case(plan: dict, original_manifest: dict, *, output_dir, attempt_dir,
                     spawn=None, watch=None, clock=None,
                     guard_root=GUARD_ROOT, env=None):
    """Execute ONE remap case under the shared fail-closed guard.

    ``spawn``/``watch`` default to the real subprocess/monitor functions; they
    are injectable only so source-only tests can prove the wiring without a
    container. No case is started when reserve or exclusive slot is missing.
    """
    spawn = spawn or subprocess.Popen
    watch = watch or monitor.watch
    clock = clock or time.monotonic
    guard_root = Path(guard_root).resolve()
    env = dict(env or os.environ)
    env["CONTAINERS_STORAGE_CONF"] = str(guard_root / "storage.conf")
    output_dir, attempt_dir = Path(output_dir), Path(attempt_dir)

    # Fresh reserve check immediately before any ownership or process.
    free = exploratory_space.available(str(WORKSPACE))
    capacity = remap_runner.capacity_decision(free)
    if not capacity["capacity_admitted"]:
        return {"schema": EXECUTION_SCHEMA, "status": "failed",
                "failure_reason": "reserve_below_32gib", "capacity": capacity}

    binding_record = bind_plan_to_original_manifest(plan, original_manifest)
    cidfile = cidfile_from_argv(plan.get("argv"))
    if cidfile.exists() or cidfile.is_symlink():
        raise ValueError("exact CID file already exists")
    # The controller may already own this directory for plan/preflight
    # records; per-file exclusive creation below still prevents
    # overwriting any attempt evidence.
    attempt_dir.mkdir(parents=True, exist_ok=True)
    launcher.setup_bad_cycles(attempt_dir)
    launcher.write_receipt(
        attempt_dir, case=str(plan.get("alias")),
        attempt_id=str(plan.get("attempt_id")), argv=list(plan["argv"]),
        status="attempted")

    stdout = attempt_dir / LOG_NAMES[0]
    stderr = attempt_dir / LOG_NAMES[1]
    ident = f"remap-{plan['alias']}-{time.time_ns()}"
    counter = {"samples": 0}
    state = {"schema": EXECUTION_SCHEMA, "status": "unknown", "_start": clock(),
             "capacity": capacity, "original_input_binding": binding_record,
             "bound_cid": None, "guard_observation": None,
             "unmount_proof": None, "unmount_verified": False,
             "guard_receipt": None, "failure_reason": None}

    with (guard_root / ".global-worker.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            state.update(status="failed", failure_reason="exclusive_slot_busy")
            return state
        lease.require_clear(guard_root, env, watchdog_path=heartbeat.alive_path(guard_root))
        lease.acquire(guard_root, ident, "pilot", cidfile=cidfile)
        emitter = heartbeat.Emitter(guard_root, ident)
        emitter.before_spawn()
        proc = None
        try:
            with stdout.open("xb") as out, stderr.open("xb") as err:
                proc = spawn(list(plan["argv"]), cwd=str(guard_root), env=env,
                             stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                             start_new_session=True)
            def on_bind(bound):
                cid = bound.get("cid")
                if not isinstance(cid, str) or not HEX64.fullmatch(cid):
                    raise GuardExceeded("binding_unavailable")
                state["bound_cid"] = cid
                emitter.bound(cid)
                lease.bind_cid(guard_root, ident, cid, cidfile=cidfile,
                               pid=bound.get("pid"), fingerprint=bound.get("fingerprint"))

            cfg = {"wall_seconds": plan["guard"]["wall_seconds"],
                   "rss_bytes": plan["guard"]["rss_limit_bytes"],
                   "guard_mode": "pilot", "cidfile": cidfile, "env": env,
                   "heartbeat": lambda: counter.__setitem__("samples", counter["samples"] + 1)}
            observation = watch(proc, cfg, on_bind=on_bind)
            state["guard_observation"] = observation
            cid = state.get("bound_cid") or observation.get("cid")
            if not isinstance(cid, str) or not HEX64.fullmatch(cid):
                raise ValueError("guard observation has no bound CID")
            unmount = _unmount_proof(guard_root, env, cid, observation.get("teardown"))
            state["unmount_proof"] = unmount
            state["unmount_verified"] = True
            receipt = _guard_receipt(observation, plan=plan, samples=counter["samples"],
                                     unmount_proof=unmount)
            state["guard_receipt"] = receipt
            state["resource"] = {
                "peak_rss_bytes": observation.get("peak_rss"),
                "samples": counter["samples"],
                "observation_ended": True,
                "bound_cid": cid,
                "guard_receipt": receipt,
                METHOD_KEY: COMPARABLE_METHOD,
                VERSION_KEY: COMPARABLE_METHOD_VERSION,
                SCOPE_KEY: COMPARABLE_SCOPE,
            }
            state["returncode"] = terminate.group(proc)
            state["wall_seconds"] = round(clock() - state["_start"], 3)
            if state["returncode"] != 0:
                state.update(status="failed", failure_reason=f"exit_{state['returncode']}")
            else:
                state["status"] = "finished"
        except (GuardExceeded, ValueError, OSError, subprocess.SubprocessError) as exc:
            state.update(status="failed", failure_reason=f"{type(exc).__name__}:{exc}"[:320])
            if proc is not None:
                terminate.group(proc)
        finally:
            if state["unmount_verified"]:
                lease.release(guard_root, ident,
                              cid=state.get("bound_cid"),
                              proof=state.get("guard_observation"))
            else:
                state["lease_state"] = "active_unreleased"
            state["log_paths"] = {
                LOG_NAMES[0]: str(stdout), LOG_NAMES[1]: str(stderr)}
    return state
