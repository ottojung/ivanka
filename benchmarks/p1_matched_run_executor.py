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


def observe_container_cpu_max(env: dict[str, str], cid: str) -> str | None:
    """Read live container CPU quota via podman inspect; None if unavailable."""
    try:
        out = subprocess.run(
            ["podman", "inspect", "--format",
             "{{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}}", cid],
            env=env, check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip().split()
    except Exception:
        return None
    if len(out) != 2 or not all(part.lstrip("-").isdigit() for part in out):
        return None
    quota, period = int(out[0]), int(out[1])
    if period <= 0:
        return None
    if quota <= 0:
        return "max " + str(period)
    return str(quota) + " " + str(period)


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
) -> Callable[..., dict[str, Any]]:
    """Build a real guarded runner for live operator use.

    This wires real podman spawn, CID/launcher liveness, /proc sampling via the
    shared guard, and observed container CPU quota. It does NOT bypass the guard:
    run_prospective still enforces STOP/lease/watchdog/disk/admission. Callers
    must supply reviewed attestation and explicit operator authorization; absence
    of those inputs must refuse before spawn.
    """
    if not attestation.is_file():
        raise Refusal("deployment attestation file missing")
    deps = plan.readiness(attestation)
    if deps.get("ready") is not True:
        raise Refusal("dependencies not ready: " + "; ".join(deps.get("reasons", [])))
    run_env = dict(env or {})

    def _spawn(cidfile: str, spawn_env: dict[str, str], *, argv: list[str], arm_dir: pathlib.Path):
        return production_podman_spawn(argv, cidfile, spawn_env, arm_dir)

    def _running(proc_holder: dict[str, Any]):
        proc = proc_holder.get("proc")
        return bool(proc is not None and proc.poll() is None)

    inner_holder: dict[str, Any] = {}

    def _measure():
        # watch_bound requires a non-None measurement; actual RSS is sampled by
        # the guard's bound tree sampler.
        return True

    def _runner(step: dict[str, str], argv: list[str], arm_dir: pathlib.Path,
                *, deadline: float | None = None) -> dict[str, Any]:
        def wrapped_spawn(cidfile, spawn_env, *, argv, arm_dir):
            proc = production_podman_spawn(argv, cidfile, spawn_env, arm_dir)
            inner_holder["proc"] = proc
            return proc

        local_runner = guarded_podman_arm_runner(
            owner=owner,
            lease_root=lease_root,
            stop_path=stop_path,
            disk_path=disk_path,
            container_cpu_max="200000 100000",
            lock_path=lock_path,
            env=run_env,
            watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            host_evidence=plan.host_evidence,
            spawn=wrapped_spawn,
            running=lambda: _running(inner_holder),
            measure=_measure,
        )
        result = local_runner(step, argv, arm_dir, deadline=deadline)
        cidfiles = result.get("pinned_cidfiles") or []
        if cidfiles:
            try:
                cid = pathlib.Path(cidfiles[0]).read_text().strip()
                observed = observe_container_cpu_max(run_env, cid)
                if observed is not None:
                    result["observed_container_cpu_max"] = observed
                    if observed != "200000 100000":
                        raise Refusal("observed container cpu.max mismatch: " + observed)
            except Refusal:
                raise
            except Exception:
                pass
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
) -> dict[str, Any]:
    """Execute a previously emitted plan with an explicit arm runner."""
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
        record = plan.arm_evidence_record(
            {"case": case, "arm": arm}, before, after, timing,
            sampled_rss_bytes=raw.get("sampled_rss_bytes"),
            container_cpu_max=raw.get("container_cpu_max"),
            stage_timing=stage_timing,
            log_sha256=log_sha,
        )
        record["status"] = raw.get("status")
        record["argv_sha256"] = _sha256_bytes(json.dumps(argv, sort_keys=True).encode())
        record["contention"] = {
            "before": plan.contention_check(before),
            "after": plan.contention_check(after),
        }
        for key in ("guard_outcome", "pinned_cidfiles"):
            if key in raw:
                record[key] = raw[key]
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
