#!/usr/bin/env python3
"""Fail-closed executor for the P1 matched-resource AB/BA timing plan.

The plan module only describes a run; this module actually executes one when,
and only when, an operator supplies an explicit arm runner. Importing this
module, emitting a plan, or invoking the CLI never starts a container: the CLI
runner is the refusing default. Every arm that does run goes through the
reviewed shared guard (``fail_closed_guard.p1_harness.run_prospective``) via
``guarded_podman_arm_runner``; STOP, lease, watchdog and disk admission are
therefore enforced by that guard, not reimplemented here.

The executor writes only fresh, exclusively-created evidence under a caller
supplied output root. It never edits a historical receipt, never supplies truth
or reference data, never changes a scientific gate and makes no qualification
claim. Stage intervals and host-contention snapshots are descriptive
observations; the signed gap between official timing and logged span is kept
and explicitly marked non-causal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import p1_ultradeep_matched_runtime as plan  # noqa: E402
from fail_closed_guard import p1_harness  # noqa: E402

EXECUTOR_SCHEMA = "ivanka.p1.ultradeep-matched-run.executor.v1"
RECEIPT_SCHEMA = "ivanka.p1.ultradeep-matched-run.receipt.v1"
STAGE_ATTRIBUTION = "descriptive_elapsed_intervals_not_causal"


class Refusal(plan.Refusal):
    """A safety invariant failed; no arm may be started."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_exclusive(path: pathlib.Path, obj: dict[str, Any]) -> None:
    """Create fresh evidence; an existing record is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def default_arm_runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise Refusal("no arm runner; live execution not authorized")


REQUESTED_CPU_MAX = plan.COMPARABILITY["required_container_cpu_max"]
CPU_MAX_ORIGIN_V2 = "kernel_cgroup_v2_cpu_max"
CPU_MAX_ORIGIN_V1 = "kernel_cgroup_v1_cpu_cfs"
KERNEL_QUOTA_ORIGINS = (CPU_MAX_ORIGIN_V2, CPU_MAX_ORIGIN_V1)

# Host scope is never inferred from a /proc mount or a caller assertion; only
# a separately reviewed, structured operator proof may set host_scope_proven.
HOST_SCOPE_PROOF_SCHEMA = "ivanka.p1.host-cgroup-scope-proof.v1"


def normalize_cpu_max(raw: str) -> str | None:
    """Normalize a kernel cpu.max / CFS pair to the reviewed 'quota period' form."""
    parts = raw.split()
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        return None
    if parts[0] == "max":
        return "max " + parts[1]
    if parts[0].isdigit():
        return parts[0] + " " + parts[1]
    return None


def _quota_ratio(value: str) -> float | None:
    quota, period = value.split()
    if quota == "max":
        return float("inf")
    try:
        return int(quota) / int(period)
    except (ValueError, ZeroDivisionError):
        return None


def _cgroup_dirs(v2_path: str, cgroup_root: pathlib.Path) -> list[pathlib.Path]:
    """Every directory from the cgroup root to the process leaf, in order."""
    parts = [part for part in v2_path.split("/") if part]
    return [cgroup_root.joinpath(*parts[:index]) for index in range(len(parts) + 1)]


def _read_quota_file(path: pathlib.Path, raw: str) -> tuple[str, str | None, str | None]:
    value = normalize_cpu_max(raw)
    if value is None:
        return "unreadable", None, "malformed"
    return "ok", value, None


def kernel_cpu_max(cgroup_text: str, cgroup_root: pathlib.Path) -> dict[str, Any] | None:
    """Inspect the visible cgroup hierarchy of one live process.

    Every directory from the mounted cgroup root to the process leaf is checked.
    A missing cpu controller is distinct from an unreadable/malformed file. The
    result always records coverage, leaf status and the full normalized chain;
    it is a visible-hierarchy observation, never an absolute effective-quota
    proof unless an operator separately supplies host-scope provenance.
    """
    for line in cgroup_text.splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3:
            continue
        hierarchy, controller, path = fields
        if hierarchy != "0" or controller != "":
            continue
        directories = _cgroup_dirs(path, cgroup_root)
        chain, missing, unreadable = [], [], []
        for directory in directories:
            candidate = directory / "cpu.max"
            if candidate.is_symlink():
                unreadable.append(str(directory))
                continue
            if not candidate.is_file():
                if (directory / "cgroup.controllers").is_file():
                    missing.append(str(directory))
                else:
                    unreadable.append(str(directory))
                continue
            try:
                raw = candidate.read_text().strip()
            except OSError:
                unreadable.append(str(directory))
                continue
            status, value, reason = _read_quota_file(candidate, raw)
            if status == "ok":
                chain.append({"path": str(directory), "raw": raw,
                              "value": str(value), "status": "ok"})
            else:
                unreadable.append(str(directory))
        leaf = directories[-1]
        leaf_status = "ok" if any(item["path"] == str(leaf) for item in chain) else "unavailable"
        tightest = None
        if chain:
            tightest = min(chain, key=lambda item: _quota_ratio(item["value"]) or float("inf"))
        complete = not missing and not unreadable and leaf_status == "ok"
        return {
            "origin": CPU_MAX_ORIGIN_V2,
            "value": tightest["value"] if tightest else None,
            "raw": tightest["raw"] if tightest else None,
            "cgroup_path": path,
            "source": tightest["path"] + "/cpu.max" if tightest else None,
            "chain": chain, "chain_normalized": [
                [item["path"], item["value"]] for item in chain],
            "leaf_value": next((item["value"] for item in chain
                                if item["path"] == str(leaf)), None),
            "leaf_status": leaf_status,
            "leaf_only": len(chain) == 1 and leaf_status == "ok",
            "effective_source": tightest["path"] if complete and tightest else None,
            "coverage": {"expected": len(directories), "read": len(chain),
                         "missing": missing, "unreadable": unreadable,
                         "complete": complete},
            "scope": "visible_hierarchy_only",
            "absolute_effective_claim": False,
        }
    return None


def observe_bound_cpu_quota(table: dict[int, Any], bound: dict[str, Any],
                            cgroup_root: pathlib.Path = pathlib.Path("/sys/fs/cgroup"),
                            ) -> dict[str, Any] | None:
    """Observe quota only from the guard-bound init PID with unchanged identity."""
    if not isinstance(bound, dict):
        return None
    from fail_closed_guard import binding
    cid, pid = bound.get("cid"), bound.get("pid")
    fingerprint = bound.get("fingerprint")
    if (not isinstance(cid, str) or not binding.CID.fullmatch(cid)
            or not isinstance(pid, int) or isinstance(pid, bool)
            or not isinstance(fingerprint, (list, tuple))
            or len(fingerprint) != 2):
        return None
    record = table.get(pid) if isinstance(table, dict) else None
    if not isinstance(record, dict):
        return None
    actual = [record.get("starttime"), record.get("pid_ns")]
    if actual != list(fingerprint):
        return None
    cgroup_text = record.get("cgroup")
    if not isinstance(cgroup_text, str) or not cgroup_text.strip():
        return None
    observed = kernel_cpu_max(cgroup_text, cgroup_root)
    if observed is not None:
        observed["pid"] = pid
        observed["cgroup"] = cgroup_text
        observed["cid"] = cid
        observed["fingerprint"] = list(fingerprint)
        observed["sample_identity"] = {
            "cid": cid, "pid": pid, "fingerprint": list(fingerprint),
            "cgroup": cgroup_text,
            "chain_normalized": observed.get("chain_normalized"),
        }
    return observed


def compare_quota_samples(previous: dict[str, Any] | None,
                          current: dict[str, Any]) -> list[str]:
    """Report any change in the full bound sample, not just the quota value."""
    if previous is None:
        return []
    before = previous.get("sample_identity") or {}
    after = current.get("sample_identity") or {}
    reasons = []
    for key in ("cid", "pid", "fingerprint", "cgroup", "chain_normalized"):
        if before.get(key) != after.get(key):
            reasons.append("bound " + key + " changed")
    if previous.get("value") != current.get("value"):
        reasons.append("quota value changed")
    if (previous.get("coverage") or {}).get("complete") != (
            current.get("coverage") or {}).get("complete"):
        reasons.append("quota coverage changed")
    return reasons


def guard_terminal_proof(proof: Any, *, cid: str | None = None) -> dict[str, Any] | None:
    """Recognize only the shared guard's own exact-CID natural-exit proof.

    The guard's ``natural_exit.attest`` is the sole terminal proof: it requires
    the exact bound CID to be proven absent twice together with a real integer
    launcher result. A zombie /proc record, a launcher poll or a caller
    assertion is never a guard-owned terminal proof.
    """
    if not isinstance(proof, dict):
        return None
    from fail_closed_guard import binding
    absence = proof.get("absence_proof")
    proof_cid = proof.get("cid")
    if (proof.get("method") != "exact_cid_inspect"
            or not isinstance(proof_cid, str)
            or not binding.CID.fullmatch(proof_cid)
            or (cid is not None and proof_cid != cid)
            or isinstance(proof.get("returncode"), bool)
            or not isinstance(proof.get("returncode"), int)
            or not isinstance(absence, dict)
            or absence.get("observed_absent") is not True
            or absence.get("inspected_absent_twice") is not True):
        return None
    return proof


def host_scope_proven_from_proof(proof: Any) -> bool:
    """True only for a structured, separately attested host-scope proof.

    A bare boolean or caller assertion is never host evidence. Production has
    no such proof today, so ``host_scope_proven`` stays False and comparability
    remains diagnostic-only until an operator supplies a reviewed proof.
    """
    if not isinstance(proof, dict):
        return False
    return (proof.get("schema") == HOST_SCOPE_PROOF_SCHEMA
            and isinstance(proof.get("cgroup_root"), str)
            and bool(proof.get("cgroup_root"))
            and isinstance(proof.get("attested_by"), str)
            and bool(proof.get("attested_by")))


def guard_terminal_sample_gap(raw: dict[str, Any]) -> bool:
    """Authenticate an arm result's terminal-gap claim against the guard proof.

    ``execute_plan`` accepts a result from an arbitrary caller-supplied arm
    runner. A ``terminal_sample_gap`` claim only becomes evidence when the very
    same result carries the shared guard's own exact-CID natural-exit proof for
    the observed bound CID. A bare assertion, a foreign CID or a non-guard
    method is refused, so an unauthenticated gap cannot stick in the receipt.
    """
    if not isinstance(raw, dict) or raw.get("terminal_sample_gap") is not True:
        return False
    observed = raw.get("observed_cpu_quota")
    cid = observed.get("cid") if isinstance(observed, dict) else None
    if not isinstance(cid, str):
        return False
    from fail_closed_guard import binding
    if not binding.CID.fullmatch(cid):
        return False
    outcome = raw.get("guard_outcome")
    guard_result = outcome.get("result") if isinstance(outcome, dict) else None
    proof = guard_terminal_proof(
        guard_result.get("natural_exit") if isinstance(guard_result, dict) else None,
        cid=cid)
    return proof is not None


def sampling_gap_kind(previous: dict[str, Any] | None,
                      table: dict[int, Any], bound: dict[str, Any], *,
                      terminal_proof: Any = None) -> str | None:
    """A zombie at the bound PID is terminal only with identity and guard proof.

    State Z for the bound init PID is a natural-exit candidate only when the
    full guard-bound fingerprint (starttime, pid_ns) still matches. Even then
    it is accepted as terminal only when backed by the shared guard's own
    exact-CID natural-exit proof. PID reuse, a foreign process and a caller
    assertion without that proof are all drift.
    """
    if previous is None:
        return None
    live = table.get(bound.get("pid")) if isinstance(table, dict) else None
    if not isinstance(live, dict) or live.get("state") != "Z":
        return "drift"
    fingerprint = bound.get("fingerprint")
    if (not isinstance(fingerprint, (list, tuple)) or len(fingerprint) != 2
            or [live.get("starttime"), live.get("pid_ns")] != list(fingerprint)):
        return "drift"
    if guard_terminal_proof(terminal_proof, cid=bound.get("cid")) is None:
        return "drift"
    return "terminal"


def quota_diagnostic(observed: dict[str, Any] | None, *,
                     host_scope_proven: bool = False,
                     drift: list[str] | None = None) -> dict[str, Any]:
    """Classify an observation as evidence; never silently qualify a gap.

    Mismatch, incomplete ancestry and delegated visibility are recorded as
    diagnostics so the measured arm evidence survives even when comparability
    must fail closed.
    """
    reasons = []
    if observed is None:
        reasons.append("no observed kernel quota")
    else:
        if observed.get("origin") not in KERNEL_QUOTA_ORIGINS:
            reasons.append("non-kernel quota origin")
        if observed.get("value") != REQUESTED_CPU_MAX:
            reasons.append("quota value differs from request")
        coverage = observed.get("coverage") or {}
        if not coverage.get("complete"):
            reasons.append("invisible or unreadable cgroup ancestry")
        if observed.get("leaf_status") != "ok":
            reasons.append("leaf cpu quota unreadable")
        if not host_scope_proven:
            reasons.append("visible hierarchy only; host scope not proven")
    if drift:
        reasons.extend(drift)
    return {"matched": not reasons, "reasons": reasons,
            "host_scope_proven": bool(host_scope_proven),
            "observed_value": observed.get("value") if observed else None}


def operator_environment(storage_conf: pathlib.Path,
                         base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the real Podman environment used by spawn and shared-guard inspect.

    An empty environment makes both the launcher and the guard's exact-CID
    inspection fail before any arm can be measured. Inherit the operator shell
    only for the executable search path and home, then pin the project storage
    namespace through the reviewed shared helper so no inherited store config
    can redirect the arm.
    """
    source = dict(os.environ if base_env is None else base_env)
    for key in ("PATH", "HOME"):
        if not source.get(key):
            raise Refusal("operator environment missing " + key)
    from fail_closed_guard import store
    env = store.pin_env(source, storage_conf=storage_conf)
    if shutil.which("podman", path=env.get("PATH")) is None:
        raise Refusal("podman not found in operator PATH")
    return env


def production_podman_spawn(argv: list[str], cidfile: str, env: dict[str, str],
                            arm_dir: pathlib.Path) -> subprocess.Popen[str]:
    """Spawn a real podman arm with the guard-owned cidfile.

    The argv comes from the reviewed plan template and is re-verified before
    execution. This function only injects --cidfile; it does not alter image,
    mounts, entrypoint or user flags.
    """
    if not argv or argv[:2] != ["podman", "run"]:
        raise Refusal("production runner requires reviewed podman run argv")
    cmd = list(argv[:2]) + ["--cidfile", cidfile] + list(argv[2:])
    log_path = arm_dir / "podman.log"
    log_handle = log_path.open("ab")
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=log_handle, stderr=subprocess.STDOUT,
                                text=False)
    except Exception:
        log_handle.close()
        raise
    proc._ivanka_log_handle = log_handle  # type: ignore[attr-defined]
    return proc


def build_production_arm_runner(
    *,
    owner: str,
    lease_root: pathlib.Path,
    stop_path: pathlib.Path,
    disk_path: pathlib.Path,
    lock_path: pathlib.Path,
    watchdog_path: pathlib.Path,
    watchdog_graphroot: pathlib.Path,
    attestation: pathlib.Path,
    env: dict[str, str] | None = None,
    cgroup_root: pathlib.Path = pathlib.Path("/sys/fs/cgroup"),
    host_scope_proof: dict[str, Any] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Build a real guarded runner for live operator use.

    This wires real podman spawn, CID/launcher liveness, /proc sampling via the
    shared guard, and observed container CPU quota. It does NOT bypass the guard:
    run_prospective still enforces STOP/lease/watchdog/disk/admission. Callers
    must supply reviewed attestation and explicit operator authorization; absence
    of those inputs must refuse before spawn. ``host_scope_proof`` must be a
    separate, structured operator proof; a bare assertion cannot set
    ``host_scope_proven`` in any receipt.
    """
    if not attestation.is_file():
        raise Refusal("deployment attestation file missing")
    deps = plan.readiness(attestation)
    if deps.get("ready") is not True:
        raise Refusal("dependencies not ready: " + "; ".join(deps.get("reasons", [])))
    proven = host_scope_proven_from_proof(host_scope_proof)
    run_env = dict(env or {})

    def _spawn(cidfile: str, spawn_env: dict[str, str], *, argv: list[str], arm_dir: pathlib.Path):
        return production_podman_spawn(argv, cidfile, spawn_env, arm_dir)

    def _running(proc_holder: dict[str, Any]):
        proc = proc_holder.get("proc")
        return bool(proc is not None and proc.poll() is None)

    inner_holder: dict[str, Any] = {}
    from fail_closed_guard import binding, proc as proc_sampler

    def _measure():
        # watch_bound requires a non-None measurement; actual RSS is sampled by
        # the guard's bound tree sampler.
        return True

    def _monitored_snapshot():
        """Guard-owned PID table; observe quota only from its validated bind.

        The shared guard calls this for binding and on every watch sample. The
        exact CID, init PID and immutable fingerprint come from the guard's own
        bind_container; a changed or unreadable identity stops the observation
        instead of attributing another process's cgroup to this arm.
        """
        table = proc_sampler.snapshot()
        bound = inner_holder.get("bound")
        if bound is None:
            return table
        observed = observe_bound_cpu_quota(table, bound, cgroup_root)
        previous = inner_holder.get("observed_cpu_quota")
        if observed is not None:
            drift = compare_quota_samples(previous, observed)
            if drift:
                inner_holder["quota_drift"] = drift
            inner_holder["observed_cpu_quota"] = observed
            # The bound identity was observed live again; a prior gap cannot
            # be a terminal natural exit and must not be promoted later.
            inner_holder.pop("pending_sample_gap", None)
            return table
        if previous is not None:
            # Defer terminal classification: the guard has not produced its
            # exact-CID natural-exit proof yet at sampling time. Keep the raw
            # table so the decision uses guard-owned evidence after the run.
            inner_holder["pending_sample_gap"] = table
        return table

    def _bind(cid, env, snapshot=None):
        bound = binding.bind_container(cid, env, snapshot=snapshot)
        inner_holder["bound"] = {
            "cid": bound.get("cid"), "pid": bound.get("pid"),
            "fingerprint": bound.get("fingerprint"),
        }
        return bound

    def _runner(step: dict[str, str], argv: list[str], arm_dir: pathlib.Path,
                *, deadline: float | None = None) -> dict[str, Any]:
        inner_holder.clear()

        def wrapped_spawn(cidfile, spawn_env, *, argv, arm_dir):
            inner_holder["cidfile"] = cidfile
            spawned = production_podman_spawn(argv, cidfile, spawn_env, arm_dir)
            inner_holder["proc"] = spawned
            return spawned

        local_runner = guarded_podman_arm_runner(
            owner=owner,
            lease_root=lease_root,
            stop_path=stop_path,
            disk_path=disk_path,
            container_cpu_max=REQUESTED_CPU_MAX,
            lock_path=lock_path,
            env=run_env,
            watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            host_evidence=plan.host_evidence,
            spawn=wrapped_spawn,
            running=lambda: _running(inner_holder),
            measure=_measure,
            snapshot=_monitored_snapshot,
            bind_container=_bind,
        )
        result = local_runner(step, argv, arm_dir, deadline=deadline)
        observed = inner_holder.get("observed_cpu_quota")
        drift = list(inner_holder.get("quota_drift") or [])
        bound = inner_holder.get("bound") or {}
        guard_outcome = result.get("guard_outcome")
        guard_result = guard_outcome.get("result") if isinstance(guard_outcome, dict) else None
        proof = guard_terminal_proof(
            guard_result.get("natural_exit") if isinstance(guard_result, dict) else None,
            cid=bound.get("cid"))
        pending = inner_holder.get("pending_sample_gap")
        terminal_gap = False
        if pending is not None and observed is not None:
            if sampling_gap_kind(observed, pending, bound,
                                terminal_proof=proof) == "terminal":
                # A guard-owned natural exit legitimately ends sampling; earlier
                # samples stay as evidence and are not poisoned by the gap.
                terminal_gap = True
            else:
                drift.append("bound init disappeared or became unreadable")
        # Requested/configured values are preserved but never used as proof.
        result["requested_container_cpu_max"] = REQUESTED_CPU_MAX
        result["container_cpu_max"] = REQUESTED_CPU_MAX
        result["observed_cpu_quota"] = observed
        result["observed_container_cpu_max"] = observed.get("value") if observed else None
        result["quota_drift"] = drift
        result["terminal_sample_gap"] = terminal_gap
        result["host_scope_proven"] = proven
        # Carry the structured proof (never a bare assertion) so execute_plan
        # can re-derive the host-scope claim from guarded evidence.
        result["host_scope_proof"] = host_scope_proof
        result["quota_diagnostic"] = quota_diagnostic(
            observed, host_scope_proven=proven, drift=drift)
        return result

    return _runner


def _require_ready(emitted_plan: dict[str, Any], *, allow_unready: bool = False) -> None:
    if emitted_plan.get("schema") != plan.SCHEMA:
        raise Refusal("unexpected plan schema")
    deps = emitted_plan.get("dependencies") or {}
    if deps.get("ready") is not True:
        if allow_unready:
            # Test-only seam; never exposed on the command line.
            return
        reasons = deps.get("reasons") or ["dependencies not ready"]
        raise Refusal("dependencies not ready: " + "; ".join(str(r) for r in reasons))
    if emitted_plan.get("execution") != "blocked":
        # build_plan always emits blocked; the executor owns execution.
        raise Refusal("unexpected plan execution state")


TIMING_ORIGIN = "micall_in_container_monotonic_v1"


def _normalize_timing(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Refusal("missing timing record")
    seconds = raw.get("seconds")
    max_seconds = int(plan.CONSTRAINTS["timeout"])
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds <= 0 or seconds > max_seconds):
        raise Refusal("invalid timing seconds")
    origin = raw.get("timing_origin")
    if origin != TIMING_ORIGIN:
        raise Refusal("missing or unexpected timing origin")
    exit_code = raw.get("exit_code")
    if exit_code != 0:
        raise Refusal("arm exited with code " + repr(exit_code))
    return {"seconds": float(seconds), "timing_origin": origin,
            "exit_code": exit_code}


def _read_log(arm_dir: pathlib.Path, result: dict[str, Any]) -> tuple[str | None, str | None]:
    log_text = result.get("log_text")
    if isinstance(log_text, str):
        return log_text, _sha256_bytes(log_text.encode("utf-8", "replace"))
    log_path = result.get("log_path")
    candidates = []
    if isinstance(log_path, (str, pathlib.Path)):
        candidates.append(pathlib.Path(log_path))
    candidates.extend(arm_dir / name for name in ("podman.log", "stderr.log", "stdout.log"))
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            data = candidate.read_bytes()
            return data.decode("utf-8", "replace"), _sha256_bytes(data)
    return None, None


def _stage_timing(log_text: str | None, seconds: float) -> dict[str, Any] | None:
    if log_text is None:
        return None
    parsed = plan.stage_timing_from_log(log_text, seconds)
    if parsed is None:
        return None
    attributed = dict(parsed)
    attributed["attribution"] = STAGE_ATTRIBUTION
    attributed["official_seconds"] = seconds
    return attributed


def guarded_podman_arm_runner(
    *,
    owner: str,
    lease_root: pathlib.Path,
    stop_path: pathlib.Path,
    disk_path: pathlib.Path,
    container_cpu_max: str,
    lock_path: pathlib.Path | None = None,
    lock: Any = None,
    env: dict[str, str] | None = None,
    watchdog_ready: Callable[[], dict[str, Any]] | None = None,
    watchdog_path: pathlib.Path | None = None,
    watchdog_graphroot: pathlib.Path | None = None,
    watchdog_snapshot: Callable[[], Any] | None = None,
    watchdog_wall: Any = None,
    disk_usage: Callable[[pathlib.Path], Any] | None = None,
    disk_reserve_bytes: int | None = None,
    host_evidence: Callable[[], dict[str, Any]] | None = None,
    spawn: Callable[..., Any] | None = None,
    running: Callable[[], bool] | None = None,
    measure: Callable[[], Any] | None = None,
    snapshot: Callable[[], Any] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    stop_cid: Callable[[str], dict[str, Any]] | None = None,
    bind_container: Callable[..., dict[str, Any]] | None = None,
    attestation: dict[str, Any] | None = None,
    launcher: Any = None,
    audit: Callable[..., Any] | None = None,
    interval: float = 0.5,
) -> Callable[..., dict[str, Any]]:
    """Build a one-arm runner wired to the reviewed shared guard.

    The operator supplies STOP/lease/watchdog/disk inputs and the live spawn,
    liveness, measurement and container-binding callbacks. The runner itself
    creates no images and makes no deployment change. Every call enters
    ``run_prospective``; a closed gate fails the arm before any spawn. Tests
    inject the same seams and therefore exercise the real guard code path.
    """
    try:
        quota_cpus = plan.effective_cpus(container_cpu_max)
    except ValueError as exc:
        raise Refusal("invalid container cpu.max") from exc
    if quota_cpus != plan.COMPARABILITY["required_container_effective_cpus"]:
        raise Refusal("container cpu.max does not match the matched-resource pin")
    if running is None or measure is None:
        raise Refusal("guarded runner requires running and measure callbacks")
    sample_host = host_evidence or plan.host_evidence

    def _runner(
        step: dict[str, str],
        argv: list[str],
        arm_dir: pathlib.Path,
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        if arm_dir.exists() and any(arm_dir.iterdir()):
            raise Refusal("arm evidence path is not fresh: " + str(arm_dir))
        arm_dir.mkdir(parents=True, exist_ok=True)
        timing_path = arm_dir / "timing.json"
        log_path = arm_dir / "podman.log"
        pinned_cidfiles: list[str] = []
        host_before = sample_host()

        def _spawn(cidfile: str, spawn_env: dict[str, str]) -> Any:
            if spawn is None:
                raise Refusal("no live spawn supplied; refusing container execution")
            pinned_cidfiles.append(cidfile)
            return spawn(cidfile, spawn_env, argv=argv, arm_dir=arm_dir)

        kwargs: dict[str, Any] = {
            "owner": owner,
            "lease_root": lease_root,
            "stop_path": stop_path,
            "disk_path": disk_path,
            "spawn": _spawn,
            "env": dict(env or {}),
            "watchdog_ready": watchdog_ready,
            "watchdog_path": watchdog_path,
            "watchdog_graphroot": watchdog_graphroot,
            "watchdog_snapshot": watchdog_snapshot,
            "watchdog_wall": watchdog_wall,
            "disk_usage": disk_usage,
            "limit": int(plan.CONSTRAINTS["memory"]),
            "wall_seconds": int(plan.CONSTRAINTS["timeout"]),
            "deadline_utc": deadline,
            "running": running,
            "measure": measure,
            "snapshot": snapshot,
            "clock": clock,
            "sleep": sleep,
            "stop_cid": stop_cid,
            "bind_container": bind_container,
            "attestation": attestation,
            "launcher": launcher,
            "audit": audit,
            "interval": interval,
        }
        if lock is not None:
            kwargs["lock"] = lock
        elif lock_path is not None:
            kwargs["lock_path"] = lock_path
        if disk_reserve_bytes is not None:
            kwargs["disk_reserve_bytes"] = disk_reserve_bytes

        try:
            outcome = p1_harness.run_prospective(**kwargs)
        except Refusal:
            raise
        except Exception as exc:
            raise Refusal("shared guard refused arm: " + str(exc)[:200]) from exc
        if not isinstance(outcome, dict) or outcome.get("status") != "completed":
            raise Refusal("shared guard did not complete arm")
        result = outcome.get("result")
        if not isinstance(result, dict):
            raise Refusal("shared guard returned no result")
        try:
            timing = _normalize_timing(json.loads(timing_path.read_text()))
        except (OSError, ValueError) as exc:
            raise Refusal("fresh arm timing unavailable") from exc
        peak = result.get("peak_rss")
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or peak <= 0:
            raise Refusal("shared guard reported no sampled RSS")
        log_text, log_sha = _read_log(arm_dir, {"log_path": log_path})
        return {
            "status": outcome["status"],
            "timing": timing,
            "exit_code": timing["exit_code"],
            "log_path": str(log_path) if log_path.is_file() else None,
            "log_sha256": log_sha,
            "sampled_rss_bytes": int(peak),
            "container_cpu_max": container_cpu_max,
            "host_before": host_before,
            "host_after": sample_host(),
            "stage_timing": _stage_timing(log_text, timing["seconds"]),
            "guard_outcome": outcome,
            "pinned_cidfiles": pinned_cidfiles,
        }

    return _runner


def summarize_tail_vs_control(
    records: list[dict[str, Any]],
    cases: tuple[str, ...],
) -> dict[str, Any]:
    """Describe fresh paired deltas only; never substitute historical times."""
    by_case: dict[str, dict[str, float]] = {}
    incomplete: list[str] = []
    for case in cases:
        arms: dict[str, float] = {}
        for record in records:
            if record.get("case") != case or record.get("status") != "completed":
                continue
            wall = record.get("wall_seconds")
            if isinstance(wall, (int, float)) and not isinstance(wall, bool):
                arms[str(record.get("arm"))] = float(wall)
        if set(arms) != {"frozen", "candidate"}:
            incomplete.append(case)
            continue
        by_case[case] = arms["candidate"] - arms["frozen"]

    def group(names: tuple[str, ...]) -> dict[str, Any]:
        values = [by_case[name] for name in names if name in by_case]
        return {"cases": [name for name in names if name in by_case],
                "n": len(values), "candidate_minus_frozen_seconds": values,
                "mean_seconds": (sum(values) / len(values)) if values else None}

    tails = tuple(c for c in plan.CASES if c in cases)
    controls = tuple(c for c in plan.CONTROL_CASES if c in cases)
    return {
        "source": "fresh_prospective_arm_records_only",
        "comparison": "candidate_minus_frozen_seconds (negative means candidate faster)",
        "tails": group(tails),
        "controls": group(controls),
        "incomplete_cases": sorted(incomplete),
        "psi_computed": False,
        "formal_qualification": False,
        "attribution": STAGE_ATTRIBUTION,
    }


def execute_plan(
    emitted_plan: dict[str, Any],
    *,
    output_root: pathlib.Path,
    arm_runner: Callable[..., dict[str, Any]] = default_arm_runner,
    allow_unready: bool = False,
    host_evidence: Callable[[], dict[str, Any]] | None = None,
    host_scope_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a previously emitted plan with an explicit arm runner.

    Terminal-gap and host-scope claims are re-derived here from authenticated
    proofs; they are never copied from an arbitrary arm runner result. With no
    structured proof, ``host_scope_proven`` stays False and comparability
    remains diagnostic-only.
    """
    if arm_runner is default_arm_runner:
        raise Refusal("no arm runner; live execution not authorized")
    _require_ready(emitted_plan, allow_unready=allow_unready)
    sample_host = host_evidence or plan.host_evidence
    root = plan.check_output_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    schedule = emitted_plan.get("schedule")
    cases = tuple(emitted_plan.get("cases") or plan.CASES)
    if not isinstance(schedule, list) or not schedule:
        raise Refusal("empty schedule")
    expected_steps = plan.alternating_schedule(cases)
    if len(schedule) != len(expected_steps):
        raise Refusal("schedule length does not match cases")
    plan_root = pathlib.Path(str(emitted_plan.get("output_root")))
    if plan_root.expanduser().resolve() != root.resolve():
        raise Refusal("output root does not match emitted plan output root")

    # Fail closed before any arm: validate the full schedule up front so a
    # tampered or malformed later step cannot execute after earlier arms ran.
    validated: list[tuple[dict[str, str], list[str]]] = []
    for index, step in enumerate(schedule):
        if not isinstance(step, dict):
            raise Refusal("invalid schedule step")
        expected = expected_steps[index]
        if step.get("case") != expected["case"] or step.get("arm") != expected["arm"]:
            raise Refusal("schedule step deviates from deterministic AB/BA alternation")
        case = str(step["case"])
        arm = str(step["arm"])
        argv = step.get("argv")
        if argv != plan.argv_for(step, plan_root):
            raise Refusal("argv deviates from the reviewed template for " + case + "/" + arm)
        validated.append(({"case": case, "arm": arm}, list(argv)))

    records: list[dict[str, Any]] = []
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for step, argv in validated:
        case = step["case"]
        arm = step["arm"]
        arm_dir = root / case / arm
        before_default = sample_host()
        preflight = plan.contention_check(before_default)
        if preflight["abort"]:
            raise Refusal(
                "host contention before " + case + "/" + arm + ": "
                + ", ".join(preflight["reasons"]))
        raw = arm_runner(step, list(argv), arm_dir)
        if not isinstance(raw, dict):
            raise Refusal("arm runner returned invalid result")
        # Re-authenticate the host-scope claim for this arm. An explicit,
        # separately reviewed proof takes precedence; otherwise only a
        # structured proof carried by the guarded runner is recognizable.
        proof = host_scope_proof if host_scope_proof is not None else raw.get("host_scope_proof")
        proven = host_scope_proven_from_proof(proof)
        before = raw.get("host_before") if isinstance(raw.get("host_before"), dict) else before_default
        after = raw.get("host_after") if isinstance(raw.get("host_after"), dict) else sample_host()
        timing = _normalize_timing(raw.get("timing"))
        log_text, log_sha = _read_log(arm_dir, raw)
        raw_log_sha = raw.get("log_sha256")
        if isinstance(raw_log_sha, str):
            if log_sha is not None and raw_log_sha != log_sha:
                raise Refusal("log sha mismatch for " + case + "/" + arm)
            if log_sha is None:
                log_sha = raw_log_sha
        stage_timing = raw.get("stage_timing")
        if stage_timing is None and log_text is not None:
            stage_timing = _stage_timing(log_text, timing["seconds"])
        raw_diagnostic = raw.get("quota_diagnostic")
        claim_diagnostic = dict(raw_diagnostic) if isinstance(raw_diagnostic, dict) else raw_diagnostic
        if isinstance(claim_diagnostic, dict):
            claim_diagnostic["host_scope_proven"] = proven
        record = plan.arm_evidence_record(
            {"case": case, "arm": arm}, before, after, timing,
            sampled_rss_bytes=raw.get("sampled_rss_bytes"),
            container_cpu_max=raw.get("container_cpu_max"),
            requested_cpu_max=raw.get("requested_container_cpu_max"),
            observed_cpu_quota=raw.get("observed_cpu_quota"),
            quota_diagnostic=claim_diagnostic,
            quota_drift=raw.get("quota_drift"),
            stage_timing=stage_timing,
            log_sha256=log_sha,
        )
        record["status"] = raw.get("status")
        record["argv_sha256"] = _sha256_bytes(json.dumps(argv, sort_keys=True).encode())
        record["contention"] = {
            "before": plan.contention_check(before),
            "after": plan.contention_check(after),
        }
        for key in ("guard_outcome", "pinned_cidfiles",
                    "requested_container_cpu_max", "observed_cpu_quota",
                    "observed_container_cpu_max", "quota_drift"):
            if key in raw:
                record[key] = raw[key]
        record["quota_diagnostic"] = claim_diagnostic
        # Gap and host-scope claims are authenticated here, never inherited
        # from an arbitrary arm runner result.
        terminal_gap = guard_terminal_sample_gap(raw)
        record["terminal_sample_gap"] = terminal_gap
        record["host_scope_proven"] = proven
        if raw.get("terminal_sample_gap") is True and not terminal_gap:
            record["cpu_quota_drift"] = list(record.get("cpu_quota_drift") or []) + [
                "unauthenticated terminal_sample_gap claim refused"]
        _write_json_exclusive(arm_dir / "argv.json", {
            "case": case, "arm": arm, "argv": argv,
            "argv_sha256": record["argv_sha256"], "image": record["image"],
        })
        _write_json_exclusive(arm_dir / "host-evidence.json", record)
        records.append(record)

    comparability = plan.comparability_check(records, cases=cases)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "executor_schema": EXECUTOR_SCHEMA,
        "plan_schema": emitted_plan.get("schema"),
        "started_at_utc": started,
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases": list(cases),
        "schedule_len": len(schedule),
        "records": records,
        "comparability": comparability,
        "tail_vs_control": summarize_tail_vs_control(records, cases),
        "execution": "executed",
        "scientific_gates_changed": False,
        "formal_qualification": False,
    }
    _write_json_exclusive(root / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--attestation", type=pathlib.Path)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--cases", default=",".join(plan.CASES))
    parser.add_argument("--arm-runner", choices=["refuse", "production"],
                        default="refuse")
    parser.add_argument("--owner")
    parser.add_argument("--lease-root", type=pathlib.Path)
    parser.add_argument("--stop-path", type=pathlib.Path)
    parser.add_argument("--disk-path", type=pathlib.Path)
    parser.add_argument("--lock-path", type=pathlib.Path)
    parser.add_argument("--watchdog-path", type=pathlib.Path)
    parser.add_argument("--watchdog-graphroot", type=pathlib.Path)
    parser.add_argument("--storage-conf", type=pathlib.Path,
                        help="reviewed Podman storage.conf; required for --arm-runner production")
    args = parser.parse_args()
    cases = tuple(c.strip() for c in args.cases.split(",") if c.strip())
    try:
        emitted_plan = plan.build_plan(
            args.receipt, args.output_root, verify_files=args.verify_files,
            attestation=args.attestation, cases=cases)
        if args.arm_runner == "production":
            required = {
                "--owner": args.owner,
                "--lease-root": args.lease_root,
                "--stop-path": args.stop_path,
                "--disk-path": args.disk_path,
                "--lock-path": args.lock_path,
                "--watchdog-path": args.watchdog_path,
                "--watchdog-graphroot": args.watchdog_graphroot,
                "--attestation": args.attestation,
                "--storage-conf": args.storage_conf,
            }
            missing = [k for k, v in required.items() if v is None]
            if missing:
                raise Refusal("production runner missing required args: " + ", ".join(missing))
            runner = build_production_arm_runner(
                owner=args.owner,
                lease_root=args.lease_root,
                stop_path=args.stop_path,
                disk_path=args.disk_path,
                lock_path=args.lock_path,
                watchdog_path=args.watchdog_path,
                watchdog_graphroot=args.watchdog_graphroot,
                attestation=args.attestation,
                env=operator_environment(args.storage_conf),
            )
        else:
            runner = default_arm_runner
        receipt = execute_plan(emitted_plan, output_root=args.output_root,
                               arm_runner=runner)
    except plan.Refusal as exc:
        sys.stdout.write(json.dumps({
            "schema": RECEIPT_SCHEMA, "execution": "refused",
            "reason": str(exc), "formal_qualification": False,
        }, indent=2, sort_keys=True) + "\n")
        raise SystemExit(2) from exc
    sys.stdout.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
