#!/usr/bin/env python3
"""Operator-ready matched-resource executor for the P1 ultradeep timing plan.

This module executes only when explicit gates pass and an explicit arm runner is
supplied. The default runner refuses. Live container execution is never started
by import, by plan emission, or by default. When an arm runner is supplied it is
expected to reuse the reviewed shared guard (`fail_closed_guard.p1_harness`) for
each arm; this module records fresh exact receipts and stage/host attribution.

No historical receipt is modified. No scientific gate or qualification is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
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


class Refusal(plan.Refusal):
    """Executor refusal; no arm may be started."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: pathlib.Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def default_arm_runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise Refusal("no arm runner; live execution not authorized")


def _require_ready(emitted_plan: dict[str, Any], *, allow_unready: bool = False) -> None:
    deps = emitted_plan.get("dependencies") or {}
    if deps.get("ready") is not True:
        reasons = deps.get("reasons") or ["dependencies not ready"]
        if allow_unready:
            return
        raise Refusal("dependencies not ready: " + "; ".join(str(r) for r in reasons))
    if emitted_plan.get("execution") != "blocked":
        # build_plan always emits blocked; executor owns execution decision.
        raise Refusal("unexpected plan execution state")


def _normalize_timing(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Refusal("missing timing record")
    seconds = raw.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise Refusal("invalid timing seconds")
    if seconds <= 0:
        raise Refusal("invalid timing seconds")
    return {
        "seconds": float(seconds),
        "timing_origin": raw.get("timing_origin"),
        "exit_code": raw.get("exit_code"),
    }


def _read_log(arm_dir: pathlib.Path, result: dict[str, Any]) -> tuple[str | None, str | None]:
    log_text = result.get("log_text")
    if isinstance(log_text, str):
        return log_text, _sha256_bytes(log_text.encode("utf-8", "replace"))
    log_path = result.get("log_path")
    if isinstance(log_path, (str, pathlib.Path)):
        p = pathlib.Path(log_path)
        if p.is_file():
            data = p.read_bytes()
            return data.decode("utf-8", "replace"), _sha256_bytes(data)
    for name in ("podman.log", "stderr.log", "stdout.log"):
        p = arm_dir / name
        if p.is_file():
            data = p.read_bytes()
            return data.decode("utf-8", "replace"), _sha256_bytes(data)
    return None, None


def guarded_podman_arm_runner(
    *,
    owner: str,
    lease_root: pathlib.Path,
    stop_path: pathlib.Path,
    disk_path: pathlib.Path,
    lock_path: pathlib.Path | None = None,
    watchdog_ready: Callable[[], dict[str, Any]] | None = None,
    watchdog_path: pathlib.Path | None = None,
    watchdog_graphroot: pathlib.Path | None = None,
    disk_usage: Callable[[pathlib.Path], Any] | None = None,
    spawn: Callable[..., Any] | None = None,
    running: Callable[[], bool] | None = None,
    measure: Callable[[], Any] | None = None,
    snapshot: Callable[[], Any] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    stop_cid: Callable[[str], dict[str, Any]] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Build an arm runner wired to the shared fail_closed_guard.p1_harness.

    The returned runner executes exactly one arm through `run_prospective`.
    It does not start anything unless called, and `run_prospective` will refuse
    unless stop/lease/watchdog/disk/lock gates are satisfied. Callers supply the
    guard inputs; tests may inject spawn/running/measure/snapshot/clock/sleep.
    """

    def _runner(
        step: dict[str, str],
        argv: list[str],
        arm_dir: pathlib.Path,
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        arm_dir.mkdir(parents=True, exist_ok=True)
        log_path = arm_dir / "podman.log"
        timing_path = arm_dir / "timing.json"
        cidfile = arm_dir / "cidfile"

        def _spawn(_cidfile: str, env: dict[str, str]) -> Any:
            # The real spawn is supplied by the operator; tests inject it.
            if spawn is None:
                raise Refusal("no live spawn supplied; refusing container execution")
            return spawn(_cidfile, env, argv=argv, arm_dir=arm_dir)

        if running is None or measure is None:
            raise Refusal("guarded runner requires running and measure callbacks")

        outcome = p1_harness.run_prospective(
            owner=owner,
            lease_root=lease_root,
            stop_path=stop_path,
            disk_path=disk_path,
            spawn=_spawn,
            lock_path=lock_path,
            watchdog_ready=watchdog_ready,
            watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            disk_usage=disk_usage,
            limit=int(plan.CONSTRAINTS["memory"]),
            wall_seconds=int(plan.CONSTRAINTS["timeout"]),
            deadline_utc=deadline,
            running=running,
            measure=measure,
            snapshot=snapshot,
            clock=clock,
            sleep=sleep,
            stop_cid=stop_cid,
        )
        # run_prospective returns a guard outcome; the arm runner normalizes it.
        result = outcome.get("result") if isinstance(outcome, dict) else None
        timing = {}
        if timing_path.is_file():
            try:
                timing = json.loads(timing_path.read_text())
            except Exception:
                timing = {}
        guard_result = result if isinstance(result, dict) else {}
        return {
            "status": outcome.get("status") if isinstance(outcome, dict) else "unknown",
            "timing": timing,
            "exit_code": timing.get("exit_code"),
            "log_path": str(log_path) if log_path.exists() else None,
            "sampled_rss_bytes": guard_result.get("peak_rss"),
            "container_cpu_max": plan.CONSTRAINTS["cpus"] and "200000 100000",
            "host_after": plan.host_evidence(),
            "guard_outcome": outcome,
        }

    return _runner


def execute_plan(
    emitted_plan: dict[str, Any],
    *,
    output_root: pathlib.Path,
    arm_runner: Callable[..., dict[str, Any]] = default_arm_runner,
    allow_unready: bool = False,
) -> dict[str, Any]:
    """Execute a previously emitted plan with an explicit arm runner.

    Fails closed unless dependencies are ready (or allow_unready is explicitly
    set for a test-only dry execution) and a non-default arm runner is used.
    """
    if arm_runner is default_arm_runner:
        raise Refusal("no arm runner; live execution not authorized")
    _require_ready(emitted_plan, allow_unready=allow_unready)
    root = plan.check_output_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    schedule = emitted_plan.get("schedule") or []
    if not isinstance(schedule, list) or not schedule:
        raise Refusal("empty schedule")
    cases = tuple(emitted_plan.get("cases") or plan.CASES)
    records: list[dict[str, Any]] = []
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for step in schedule:
        if not isinstance(step, dict):
            raise Refusal("invalid schedule step")
        case = str(step.get("case"))
        arm = str(step.get("arm"))
        argv = step.get("argv")
        if not isinstance(argv, list) or not argv:
            raise Refusal("invalid argv for " + case + "/" + arm)
        arm_dir = root / case / arm
        before_default = plan.host_evidence()
        raw = arm_runner(step, argv, arm_dir)
        if not isinstance(raw, dict):
            raise Refusal("arm runner returned invalid result")
        before = raw.get("host_before") if isinstance(raw.get("host_before"), dict) else before_default
        after = raw.get("host_after") if isinstance(raw.get("host_after"), dict) else plan.host_evidence()
        timing = _normalize_timing(raw.get("timing"))
        log_text, log_sha = _read_log(arm_dir, raw)
        stage_timing = raw.get("stage_timing")
        if stage_timing is None and log_text is not None:
            stage_timing = plan.stage_timing_from_log(log_text, timing.get("seconds"))
        record = plan.arm_evidence_record(
            {"case": case, "arm": arm},
            before,
            after,
            timing,
            sampled_rss_bytes=raw.get("sampled_rss_bytes"),
            container_cpu_max=raw.get("container_cpu_max"),
            stage_timing=stage_timing,
            log_sha256=log_sha,
        )
        record["argv_sha256"] = _sha256_bytes(json.dumps(argv, sort_keys=True).encode())
        record["status"] = raw.get("status")
        _write_json(arm_dir / "host-evidence.json", record)
        records.append(record)
    comparability = plan.comparability_check(records, cases=cases)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "executor_schema": EXECUTOR_SCHEMA,
        "started_at_utc": started,
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan_schema": emitted_plan.get("schema"),
        "cases": list(cases),
        "schedule_len": len(schedule),
        "records": records,
        "comparability": comparability,
        "execution": "executed",
        "scientific_gates_changed": False,
        "formal_qualification": False,
    }
    _write_json(root / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--attestation", type=pathlib.Path)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--cases", default=",".join(plan.CASES))
    parser.add_argument("--allow-unready", action="store_true")
    args = parser.parse_args()
    cases = tuple(c.strip() for c in args.cases.split(",") if c.strip())
    emitted_plan = plan.build_plan(
        args.receipt, args.output_root, verify_files=args.verify_files,
        attestation=args.attestation, cases=cases)
    # CLI default is fail-closed: no arm runner.
    receipt = execute_plan(
        emitted_plan, output_root=args.output_root,
        arm_runner=default_arm_runner, allow_unready=args.allow_unready)
    sys.stdout.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
