"""Bounded prospective P1 pilot runner on the shared fail_closed_guard.

Production entrypoint for isolated prospective pilot cases. It does not rerun
full464 and never uses hidden truth at assembly time. Truth is read only after
the guarded container exits, by the post-hoc scorer, exactly as the full-464
controller does.

The runner delegates pre-spawn gates, exact-CID binding, watchdog readiness,
sampled RSS observation, absolute deadline enforcement, teardown proof and
owner-bound STOP retirement to ``fail_closed_guard.p1_harness.run_prospective``.
No name-based kill, no launcher-process RSS claim, and no competing guard
abstraction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path

from benchmarks.assembler_bench.sam_metrics import public_diagnostics
from benchmarks.fail_closed_guard import heartbeat as hb
from benchmarks.fail_closed_guard import p1_harness, stop as guard_stop
from benchmarks.fail_closed_guard.errors import GuardExceeded
from benchmarks.podman_full_micall import score_outputs
from benchmarks.retained_artifacts import seal_terminal_evidence, terminal_retire

from .micall_dominant import MULTITRUTH_SCORE_ORIGIN, evaluate_final_alignment
from .micall_synthetic_constants import TIMING_ORIGIN
from .p1_full464_controller import (
    ADMISSION_GIB,
    DEFAULT_COMMIT,
    DEFAULT_DATA,
    DEFAULT_FROZEN,
    DEFAULT_IMAGE,
    DEFAULT_STORAGE_CONF,
    DEFAULT_TIMER,
    MEMORY_BYTES,
    ORIGINAL_IVANKA_IMAGE,
    PINS,
    PODMAN_TIMEOUT_SECONDS,
    RESERVE_GIB,
    WALL_CAP_SECONDS,
    assert_reference_blind,
    atomic_append,
    atomic_json,
    candidate_source_hashes,
    input_fingerprint,
    load_frozen,
    podman_env,
    sha256,
    verify_candidate_image,
    verify_case_hashes,
)

SCHEMA = "ivanka.p1.bounded-pilot-runner.v1"
STATUS = "ATTEMPTED_NOT_QUALIFIED"
DEFAULT_LOCK = "/workspace/ivanka-p1-component-image-20261124/pilot.lock"
# Explicit bounded pilot case list: small, no full464 rerun. These are control
# cases present in the 2026-11-25 diagnostic snapshot; they exercise the
# guarded runner without making any qualification claim.
DEFAULT_CASES = (
    "clonal-s000",
    "hcv_v3_15pct-s000",
    "hcv_hiv_30pct-s000",
)
DEFAULT_STOP = "/workspace/ivanka-p1-component-image-20261124/p1-prospective.STOP"
DEFAULT_LEASE_ROOT = "/workspace/ivanka-p1-component-image-20261124/p1-prospective-leases"
DEFAULT_EVIDENCE_ROOT = "/workspace/ivanka-p1-bounded-pilot-evidence"


def build_command(case_dir, output_dir, image, timer, container_name, cidfile):
    """Exact integrated MiCall command with a harness-pinned cidfile.

    Truth/reference inputs are never mounted; assert_reference_blind enforces the
    mount and argv contract before spawn.
    """
    return [
        "podman", "run", "--pull=never", "--network=none",
        "--userns=host", "--cpus=2", "--memory=" + str(MEMORY_BYTES),
        "--name", container_name, "--cidfile", str(cidfile),
        "--timeout", str(PODMAN_TIMEOUT_SECONDS), "--stop-timeout", "2",
        "-v", str(Path(case_dir) / "reads") + ":/reads:ro",
        "-v", str(Path(output_dir)) + ":/results:rw",
        "-v", str(Path(timer)) + ":/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
        "--denovo", "--keep_scratch", "--bad_cycles_csv",
        "/results/bad_cycles.csv", "--all_projects",
    ]


def wait_for_cidfile(cidfile, process, timeout=60, clock=time.monotonic,
                     sleep=time.sleep):
    """Block until Podman has written a valid CID or the spawn has failed."""
    deadline = clock() + timeout
    path = Path(cidfile)
    while clock() < deadline:
        if path.is_file() and not path.is_symlink():
            text = path.read_text().strip()
            if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                return text
        if process.poll() is not None:
            # Give Podman a final chance to flush the cidfile on fast exit.
            if path.is_file() and not path.is_symlink():
                text = path.read_text().strip()
                if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                    return text
            raise RuntimeError("podman exited before cidfile was written")
        sleep(0.2)
    raise RuntimeError("cidfile was not written before spawn timeout")


def verify_image(image, commit, env):
    """Reuse the full-464 candidate image contract before any case runs."""
    labels = verify_candidate_image(image, commit, env)
    if image == ORIGINAL_IVANKA_IMAGE:
        raise ValueError("original frozen Ivanka image may not be rerun")
    return labels


def verify_pins(data, frozen_path, timer, gate=None):
    """Fail closed if any frozen input/score pin differs."""
    for path, pin in ((Path(data) / "cohort.json", PINS["cohort.json"]),
                      (Path(frozen_path), PINS["phase-synthetic464/results.jsonl"]),
                      (Path(timer), PINS["inside_container_timing.py"])):
        actual = sha256(path)
        if actual != pin:
            raise ValueError(f"source hash gate failed for {path}")
    if gate is not None:
        gate_pin = PINS.get("gate_multitruth.py")
        if gate_pin and sha256(gate) != gate_pin:
            raise ValueError(f"source hash gate failed for {gate}")
    return {str(Path(p)): sha256(p) for p, _ in (
        (Path(data) / "cohort.json", None),
        (Path(frozen_path), None),
        (Path(timer), None),
    )}


class CaseExecution:
    """Mutable per-case holder shared by spawn/running/measure closures."""

    def __init__(self, command, env, log_path):
        self.command = list(command)
        self.env = dict(env)
        self.log_path = Path(log_path)
        self.process = None
        self.started = None
        self.log_handle = None

    def spawn(self, cidfile, env, timeout=60):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.log_path.open("wb")
        self.process = subprocess.Popen(
            self.command, env=self.env, stdout=self.log_handle,
            stderr=subprocess.STDOUT)
        self.started = time.monotonic()
        wait_for_cidfile(cidfile, self.process, timeout=timeout)
        return self.process

    def running(self):
        return self.process is not None and self.process.poll() is None

    def measure(self):
        # watch_bound computes tree RSS from the bound CID; this hook only
        # asserts that a measurement was possible.
        return True

    def close(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None


def seal_case_evidence(destination, record, source_hashes, env):
    """Seal exact post-hoc evidence, then retire scratch only after proof."""
    path = Path(destination)
    success = record.get("status") == "success"
    if success:
        metrics = score_outputs(path, None)
        diagnostics = public_diagnostics(path)
        evidence = {
            "metrics": metrics,
            "public_diagnostics": diagnostics,
            "candidate": dict(record),
        }
    else:
        log = path / "podman.log"
        evidence = {"failure": {
            "exit_code": record.get("exit_code"),
            "error": record.get("error"),
            "error_tail": log.read_text()[-1200:] if log.is_file() else "",
            "container_wall_seconds": record.get("wall_seconds"),
        }}
    evidence_path, _ = seal_terminal_evidence(path, evidence, source_hashes)
    return terminal_retire(
        path, evidence_path=evidence_path,
        container_dead=lambda: True, source_hashes=source_hashes)


def _case_receipt_path(destination):
    return Path(destination) / "receipt.json"


def write_case_receipt(destination, case_id, row, hashes, image, guard_result):
    receipt = {
        "schema": "ivanka.p1.bounded-pilot-case-receipt.v1",
        "status": STATUS,
        "case_id": case_id,
        "image": image,
        "case_hashes": hashes,
        "case_sha256": sha256(Path(destination) / "case.json"),
        "guard": {
            "status": guard_result.get("status"),
            "lease": guard_result.get("lease"),
            "deadline_utc": guard_result.get("deadline_utc"),
            "stop_retired_by": guard_result.get("stop_retired_by"),
            "teardown": ((guard_result.get("result") or {}).get("teardown")),
            "peak_rss": ((guard_result.get("result") or {}).get("peak_rss")),
            "rss_sample_scope": ((guard_result.get("result") or {}).get(
                "rss_sample_scope")),
            "kernel_enforcement": ((guard_result.get("result") or {}).get(
                "kernel_enforcement")),
        },
    }
    atomic_json(_case_receipt_path(destination), receipt)
    return receipt


def score_case(case_dir, destination, record, image):
    """Post-hoc scoring only: hidden truth never enters the container argv."""
    manifest_data = json.loads((Path(case_dir) / "manifest.json").read_text())
    clock = json.loads((Path(destination) / "timing.json").read_text())
    if (clock.get("timing_origin") != TIMING_ORIGIN
            or clock.get("exit_code") != 0
            or not isinstance(clock.get("seconds"), (int, float))
            or not math.isfinite(clock["seconds"]) or clock["seconds"] <= 0):
        raise ValueError("invalid in-container timing")
    metrics = evaluate_final_alignment(
        manifest_data,
        Path(case_dir) / "hidden-truth/haplotypes.fasta",
        Path(destination))
    if metrics["score_origin"] != MULTITRUTH_SCORE_ORIGIN:
        raise ValueError("wrong final MiCall score origin")
    record.update(
        status="success", seconds=clock["seconds"], timing=clock,
        score=metrics["score"], dominant_exact=metrics["dominant_exact"],
        final_dominant=metrics["source"], per_truth=metrics["source"]["per_truth"],
        sha256=image,
    )
    record["diagnostics"] = public_diagnostics(Path(destination))
    return record


def _prepare_case_dir(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"case directory already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "bad_cycles.csv").write_text("tile,cycle\n")
    return destination


def run_case(*, case_id, case_dir, destination, image, commit, timer, env,
             owner, lock_path, stop_path, lease_root, disk_path,
             case_hashes=None, watchdog_ready=None, watchdog_path=None,
             watchdog_graphroot=None, watchdog_snapshot=None,
             disk_reserve_bytes=RESERVE_GIB * 1024 ** 3,
             disk_usage=None, limit=MEMORY_BYTES,
             wall_seconds=WALL_CAP_SECONDS, deadline_utc=None,
             snapshot=None, clock=None, sleep=None, audit=None,
             bind_container=None, stop_cid_fn=None, spawn_timeout=60,
             heartbeat_root=None):
    """Run one bounded prospective case under the shared guard lifecycle."""
    case_dir = Path(case_dir)
    destination = Path(destination)
    manifest_data = json.loads((case_dir / "manifest.json").read_text())
    expected_hashes = case_hashes or manifest_data["sha256"]
    if manifest_data.get("sha256") != expected_hashes:
        raise ValueError("case manifest hash differs from frozen cohort")
    if (manifest_data["hidden_truth_file"] != "hidden-truth/haplotypes.fasta"
            or manifest_data["score_model_revision"] != 2):
        raise ValueError("case manifest differs from expected provenance")
    hashes = verify_case_hashes(case_dir, expected_hashes)

    dest = _prepare_case_dir(destination)
    container_name = "ivanka-p1-pilot-" + hashlib.sha256(
        (case_id + ":" + image + ":" + str(dest)).encode()).hexdigest()[:18]
    cidfile_holder = {}

    def command_builder(cidfile):
        command = build_command(case_dir, dest, image, timer,
                                container_name, cidfile)
        assert_reference_blind(command)
        atomic_json(dest / "argv.json", command)
        return command

    execution = CaseExecution([], env, dest / "podman.log")

    def spawn(cidfile, spawn_env):
        cidfile_holder["path"] = cidfile
        command = command_builder(cidfile)
        execution.command = command
        execution.env = dict(spawn_env)
        execution.spawn(cidfile, spawn_env, timeout=spawn_timeout)

    heartbeat_cb = None
    if heartbeat_root is not None:
        Path(heartbeat_root).mkdir(parents=True, exist_ok=True)
        emitter = hb.Emitter(heartbeat_root, owner)
        emitter.before_spawn()

        def heartbeat_cb():
            emitter.refresh()

    guard_stop.arm(stop_path, owner)
    source_hashes = candidate_source_hashes(dest, hashes, image)

    record = {
        "status": "failed", "score": 0.0,
        "score_origin": MULTITRUTH_SCORE_ORIGIN,
        "timing_origin": TIMING_ORIGIN,
        "sha256": image, "container_name": container_name,
        "exit_code": None, "per_truth": {}, "diagnostics": {},
        "argv": None,
    }

    guard_result = None
    try:
        guard_result = p1_harness.run_prospective(
            owner=owner, lease_root=lease_root, stop_path=stop_path,
            disk_path=disk_path, spawn=spawn, env=env, lock_path=lock_path,
            watchdog_ready=watchdog_ready, watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            watchdog_snapshot=watchdog_snapshot,
            disk_reserve_bytes=disk_reserve_bytes, disk_usage=disk_usage,
            limit=limit, wall_seconds=wall_seconds, deadline_utc=deadline_utc,
            running=execution.running, measure=execution.measure,
            snapshot=snapshot, clock=clock, sleep=sleep, audit=audit,
            heartbeat=heartbeat_cb, bind_container=bind_container,
            stop_cid=stop_cid_fn)
        # Guard completed: container exited and exact teardown proven.
        record["exit_code"] = (execution.process.returncode
                               if execution.process is not None else None)
        record["returncode"] = record["exit_code"]
        record["argv"] = execution.command
        guard_info = guard_result.get("result") or {}
        record["peak_sampled_rss_bytes"] = guard_info.get("peak_rss")
        record["rss_sample_scope"] = guard_info.get("rss_sample_scope")
        record["kernel_enforcement"] = guard_info.get("kernel_enforcement")
        record["teardown"] = guard_info.get("teardown")
        record["container_dead"] = True
        score_case(case_dir, dest, record, image)
    except GuardExceeded as exc:
        record["error"] = exc.reason
        record["guard_error"] = exc.reason
        record["guard_teardown_error"] = exc.teardown_error
        record["guard_result"] = exc.guard_result
        if execution.process is not None:
            record["exit_code"] = execution.process.returncode
            record["returncode"] = execution.process.returncode
        record["argv"] = execution.command
        guard_result = {"status": "fail_closed", "reason": exc.reason,
                        "result": exc.guard_result, "teardown": exc.teardown}
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["argv"] = execution.command
        guard_result = {"status": "error", "reason": record["error"],
                        "result": None}
    finally:
        execution.close()

    if record.get("status") == "success":
        try:
            verify_case_hashes(case_dir, hashes)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"post_score_input_drift:{exc}"
            record.pop("score", None)
            record["score"] = 0.0

    source_hashes = candidate_source_hashes(dest, hashes, image,
                                            {"podman.log": sha256(dest / "podman.log")}
                                            if (dest / "podman.log").is_file()
                                            else None)
    try:
        record["diagnostics"] = public_diagnostics(dest)
    except Exception as exc:
        record["diagnostics"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        record["terminal_retention"] = seal_case_evidence(
            dest, record, source_hashes, env)
    except Exception as exc:
        record["terminal_retention_error"] = f"{type(exc).__name__}: {exc}"
        record["status"] = "failed"
        if "error" not in record:
            record["error"] = record["terminal_retention_error"]

    row = {
        "schema": "ivanka.p1.bounded-pilot-case.v1",
        "status": STATUS,
        "case_id": case_id,
        "candidate_source_commit": commit,
        "candidate_image": image,
        "input_sha256": input_fingerprint(hashes),
        "case_hashes": hashes,
        "result": record,
        "guard": {
            "status": (guard_result or {}).get("status"),
            "lease": (guard_result or {}).get("lease"),
            "deadline_utc": (guard_result or {}).get("deadline_utc"),
            "stop_retired_by": (guard_result or {}).get("stop_retired_by"),
            "teardown": ((guard_result or {}).get("result") or {}).get(
                "teardown") or (guard_result or {}).get("teardown"),
            "peak_rss": ((guard_result or {}).get("result") or {}).get(
                "peak_rss"),
            "rss_sample_scope": ((guard_result or {}).get("result") or {}).get(
                "rss_sample_scope"),
            "kernel_enforcement": ((guard_result or {}).get("result") or {}).get(
                "kernel_enforcement"),
        },
    }
    atomic_json(dest / "case.json", row)
    write_case_receipt(dest, case_id, row, hashes, image, guard_result or {})
    return row


def load_case_hashes(data, frozen_path):
    """Load frozen cohort case hashes and frozen result rows by attested pins."""
    cohort = json.loads((Path(data) / "cohort.json").read_text())
    case_hashes = {entry["id"]: entry["sha256"] for entry in cohort["cases"]}
    frozen, frozen_hash = load_frozen(
        Path(frozen_path), PINS["phase-synthetic464/results.jsonl"], case_hashes)
    return case_hashes, frozen, frozen_hash


def run(args, *, env=None, image_labels=None, verify_image_fn=None,
        watchdog_ready=None, watchdog_snapshot=None, snapshot=None, clock=None,
        sleep=None, audit=None, disk_usage=None, bind_container=None,
        stop_cid_fn=None):
    data = Path(args.data).resolve()
    frozen_path = Path(args.frozen_results).resolve()
    timer = Path(args.timer).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = podman_env(args.storage_conf) if env is None else dict(env)

    selected = tuple(args.cases.split(",") if args.cases else DEFAULT_CASES)
    if not selected:
        raise ValueError("explicit case list required")
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate case in explicit case list")

    verify_pins(data, frozen_path, timer)
    if verify_image_fn is not None:
        labels = verify_image_fn(args.image, args.commit, env)
    elif image_labels is not None:
        labels = dict(image_labels)
    else:
        labels = verify_image(args.image, args.commit, env)
    case_hashes, _frozen, frozen_hash = load_case_hashes(data, frozen_path)
    unknown = [case for case in selected if case not in case_hashes]
    if unknown:
        raise ValueError(f"unknown case(s): {', '.join(unknown)}")

    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "qualified": False,
        "guard_status": "NO-GO pending independent reviewer approval",
        "candidate_source_commit": args.commit,
        "candidate_image": args.image,
        "candidate_image_labels": labels,
        "frozen_results_sha256": frozen_hash,
        "explicit_case_list": list(selected),
        "no_full464_rerun": True,
        "truth_used_at_assembly_time": False,
        "pins": PINS,
        "limits": {
            "wall_seconds": WALL_CAP_SECONDS,
            "memory_bytes": MEMORY_BYTES,
            "podman_timeout_seconds": PODMAN_TIMEOUT_SECONDS,
            "reserve_gib": RESERVE_GIB,
            "admission_gib": ADMISSION_GIB,
        },
        "paths": {
            "lock": str(args.lock),
            "stop": str(args.stop),
            "lease_root": str(args.lease_root),
            "disk_path": str(args.disk_path),
            "evidence_root": str(out),
        },
    }
    atomic_json(out / "run_manifest.json", manifest)

    owner = args.owner or f"p1-pilot:{os.getpid()}"
    results_path = out / "results.jsonl"
    completed = []
    for case_id in selected:
        case_dir = data / case_id
        destination = out / case_id
        hashes = case_hashes[case_id]
        verify_case_hashes(case_dir, hashes)
        row = run_case(
            case_id=case_id, case_dir=case_dir, destination=destination,
            image=args.image, commit=args.commit, timer=timer, env=env,
            owner=owner, lock_path=args.lock, stop_path=args.stop,
            lease_root=args.lease_root, disk_path=str(args.disk_path),
            case_hashes=hashes,
            watchdog_ready=watchdog_ready,
            watchdog_path=args.watchdog_path,
            watchdog_graphroot=args.watchdog_graphroot,
            watchdog_snapshot=watchdog_snapshot,
            snapshot=snapshot, clock=clock, sleep=sleep, audit=audit,
            disk_usage=disk_usage, bind_container=bind_container,
            stop_cid_fn=stop_cid_fn,
            disk_reserve_bytes=args.reserve_gib * 1024 ** 3,
            limit=MEMORY_BYTES, wall_seconds=WALL_CAP_SECONDS,
            heartbeat_root=args.lease_root)
        atomic_append(results_path, row)
        completed.append(row)
        print("P1_PILOT_CASE", case_id, row["result"]["status"],
              row["result"].get("error", ""), flush=True)
        if row["result"]["status"] != "success":
            break

    summary = {
        "schema": SCHEMA,
        "status": STATUS,
        "qualified": False,
        "guard_status": "NO-GO pending independent reviewer approval",
        "cases_selected": list(selected),
        "cases_completed": [row["case_id"] for row in completed],
        "cases_succeeded": [row["case_id"] for row in completed
                            if row["result"]["status"] == "success"],
        "all_succeeded": all(row["result"]["status"] == "success"
                             for row in completed) and len(completed) == len(selected),
        "manifest_sha256": sha256(out / "run_manifest.json"),
        "results_sha256": sha256(results_path) if results_path.exists() else None,
    }
    atomic_json(out / "summary.json", summary)
    print("P1_BOUNDED_PILOT", STATUS, "cases", len(completed),
          "all_succeeded", summary["all_succeeded"], flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_DATA))
    parser.add_argument("--frozen-results", type=Path,
                        default=Path(DEFAULT_FROZEN))
    parser.add_argument("--timer", type=Path, default=Path(DEFAULT_TIMER))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--storage-conf", type=Path,
                        default=Path(DEFAULT_STORAGE_CONF))
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    parser.add_argument("--stop", default=DEFAULT_STOP)
    parser.add_argument("--lease-root", default=DEFAULT_LEASE_ROOT)
    parser.add_argument("--disk-path", type=Path, default=Path("/workspace"))
    parser.add_argument("--watchdog-path", type=Path)
    parser.add_argument("--watchdog-graphroot", type=Path)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--cases",
                        help="comma-separated explicit case IDs; default is bounded pilot list")
    parser.add_argument("--reserve-gib", type=int, default=RESERVE_GIB)
    parser.add_argument("--admission-gib", type=int, default=ADMISSION_GIB)
    args = parser.parse_args(argv)
    if (args.reserve_gib, args.admission_gib) != (RESERVE_GIB, ADMISSION_GIB):
        parser.error("production disk reserve policy is fixed")
    if args.watchdog_path is None or args.watchdog_graphroot is None:
        parser.error("watchdog readiness path and graphroot are required")
    summary = run(args)
    return 0 if summary["all_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
