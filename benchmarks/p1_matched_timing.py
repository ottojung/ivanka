#!/usr/bin/env python3
"""Reproducible same-resource confirmatory timing for ultradeep-s009.

Diagnostic only. This module does NOT change any benchmark metric, gate,
qualification verdict, frozen artifact, MiCall source or container image.

One argv template is used for two arms (frozen Ivanka and the P1 candidate),
differing only in image digest, result directory and unique container name:

  --cpus=2 --memory=4000000000 --timeout 2400 --stop-timeout 2
  --network=none --userns=host --pull=never --denovo --keep_scratch
  --all_projects

The findings that motivated this plan are STRONG EVIDENCE of host/resource
drift, not causal proof: all measured MiCall stages were slower and final
outputs were byte-identical, but no controlled same-resource experiment has
yet been run. Execution is opt-in, requires the real PX global flock under an
operator-placed STOP boundary, and uses a fail-closed exact-CID RSS watcher.
With no --execute the tool only prints the plan (no subprocess, no write).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Iterator

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import p1_fail_closed_guard as guard  # noqa: E402

SCHEMA = "ivanka.p1.matched-timing.v2"
CASE = "ultradeep-s009"
PX_ROOT = pathlib.Path("/workspace/ivanka-exploratory-ten-20261121")
GLOBAL_LOCK = PX_ROOT / ".global-worker.lock"
STOP_FILE = PX_ROOT / "STOP"
LEASE_JOURNAL = PX_ROOT / ".worker-lease.jsonl"

READS = pathlib.Path(
    "/workspace/ivanka-synthetic-abundance15-464-20261117/ultradeep-s009/reads"
)
READ_SHA256 = {
    "R1.fastq.gz": "56ce9217976f60eacd2a9376f2198fa79c4cecc5cb29e19c0ebe62f2c741f5d8",
    "R2.fastq.gz": "2a72ccbde6261c28a239a439b4740eb1c5a2f879bb198f62f1440753b9a03025",
}
TIMER = pathlib.Path(
    "/workspace/micall-frozen-seven-20261117/ivanka-physical-source/"
    "benchmarks/inside_container_timing.py"
)
TIMER_SHA256 = (
    "c5baab15b8c54f27b5cfbaf459f8647707e1e9618577b803ee3440e3e661eb4e"
)
IMAGES = {
    "frozen_ivanka": (
        "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"
    ),
    "candidate_ivanka": (
        "6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971"
    ),
}
CPUS = "2"
MEMORY = "4000000000"  # matched 4 GB; not kernel-enforced on this host
TIMEOUT = "2400"  # matched 40 m
STOP_TIMEOUT = "2"
WALL_DEADLINE = 2400  # one deadline for bind + sampling + process wait
BIND_WINDOW = 30

PROTECTED_ROOTS = (
    pathlib.Path("/workspace/ivanka-p1-full464-12d8c72-20261124"),
    pathlib.Path("/workspace/micall-frozen-seven-20261117"),
    pathlib.Path("/workspace/ivanka-synthetic-abundance15-464-20261117"),
)

ARTIFACTS = (
    "conseq.csv",
    "conseq_all.csv",
    "nuc.csv.zst",
    "amino.csv.zst",
)

STAMP = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})")
ASSEMBLY = re.compile(r"Ivanka wrote (\d+) contigs in ([0-9]+(?:\.[0-9]+)?)s")
NATIVE_ASSEMBLY = re.compile(
    r"Assembled (\d+) contigs in 0:(\d\d):([0-9]+(?:\.[0-9]+)?)"
)
MARKERS = (
    "Starting on",
    "Running merge_for_entropy",
    "Running fastq_g2p",
    "Running de novo assembly",
    "Running remap",
    "Running sam2aln",
    "Running aln2counts",
    "Running coverage_plots",
    "Running cascade_report",
    "Finished sample",
)


class Refusal(Exception):
    """A safety invariant was violated; nothing was launched."""


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_inputs() -> dict[str, str]:
    found: dict[str, str] = {}
    for name, expected in READ_SHA256.items():
        path = READS / name
        if not path.is_file():
            raise Refusal(f"missing pinned read: {path}")
        actual = sha256(path)
        if actual != expected:
            raise Refusal(f"read {name} sha256 {actual} != pinned {expected}")
        found[name] = actual
    if not TIMER.is_file() or sha256(TIMER) != TIMER_SHA256:
        raise Refusal("in-container timer is missing or not the pinned revision")
    found["inside_container_timing.py"] = TIMER_SHA256
    return found


def check_output_root(raw: str) -> pathlib.Path:
    root = pathlib.Path(raw).expanduser().resolve()
    if root == pathlib.Path("/"):
        raise Refusal("output root may not be /")
    for protected in PROTECTED_ROOTS:
        resolved = protected.resolve()
        if root == resolved or resolved in root.parents or root in resolved.parents:
            raise Refusal(f"output root {root} overlaps protected {resolved}")
    if root.exists() and any(root.iterdir()):
        raise Refusal(f"output root {root} already contains files; use a fresh one")
    root.mkdir(parents=True, exist_ok=True)
    return root


def argv_for(image: str, results: pathlib.Path, arm: str) -> list[str]:
    return [
        "podman", "run", "--rm", "--pull=never", "--network=none",
        "--userns=host", "--cpus=" + CPUS, "--memory=" + MEMORY,
        "--name", f"ivanka-p1-matched-{CASE}-{arm}",
        "--timeout", TIMEOUT, "--stop-timeout", STOP_TIMEOUT,
        "-v", f"{READS}:/reads:ro", "-v", f"{results}:/results:rw",
        "-v", f"{TIMER}:/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
        "--denovo", "--keep_scratch", "--bad_cycles_csv",
        "/results/bad_cycles.csv", "--all_projects",
    ]


def _parse_stamp(text: str) -> float:
    match = STAMP.search(text)
    if not match:
        raise ValueError(f"no MiCall timestamp in {text!r}")
    date, millis = match.group(1).split(",")
    return time.mktime(time.strptime(date, "%Y-%m-%d %H:%M:%S")) + int(millis) / 1000.0


def parse_stages(log: str) -> dict[str, Any]:
    seen: list[tuple[str, float]] = []
    for line in log.splitlines():
        for marker in MARKERS:
            if marker in line and STAMP.search(line):
                seen.append((marker, _parse_stamp(line)))
                break
    native = [float(value) for _, value in ASSEMBLY.findall(log)]
    micall_native = [
        int(minutes) * 60 + float(seconds)
        for _, minutes, seconds in NATIVE_ASSEMBLY.findall(log)
    ]
    if not micall_native or not seen:
        raise ValueError("missing assembler/remap/sam2aln stage markers")
    stages: dict[str, float] = {}
    for index in range(1, len(seen)):
        name = seen[index][0]
        key, suffix = name, 1
        while key in stages:
            suffix += 1
            key = f"{name}#{suffix}"
        stages[key] = round(seen[index][1] - seen[index - 1][1], 3)
    remap = next((value for name, value in seen if name == "Running remap"), None)
    sam2aln = next((value for name, value in seen if name == "Running sam2aln"), None)
    if remap is None or sam2aln is None:
        raise ValueError("missing remap or sam2aln marker")
    return {
        "native_assembly_seconds": native[-1] if native else micall_native[-1],
        "micall_assembly_seconds": micall_native[-1],
        "remap_to_sam2aln_seconds": round(sam2aln - remap, 3),
        "stages": stages,
    }


def read_timing(path: pathlib.Path) -> dict[str, Any]:
    record = json.loads(path.read_text())
    if record.get("timing_origin") != "micall_in_container_monotonic_v1":
        raise Refusal(f"unexpected timing origin in {path}")
    if record.get("exit_code") != 0:
        raise Refusal(f"nonzero MiCall exit code in {path}")
    if not isinstance(record.get("seconds"), (int, float)) or not 0 < record["seconds"] <= WALL_DEADLINE:
        raise Refusal(f"invalid timing value in {path}")
    return record


def _host_state() -> dict[str, Any]:
    state: dict[str, Any] = {"loadavg": list(os.getloadavg()), "cpu_count": os.cpu_count()}
    quota = pathlib.Path("/sys/fs/cgroup/cpu.max")
    if quota.is_file():
        state["cgroup_cpu_max"] = quota.read_text().strip()
    return state


def _active_leases(journal: pathlib.Path) -> list[str]:
    active: dict[str, bool] = {}
    if not journal.exists():
        return []
    for line in journal.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Refusal("worker lease journal unreadable") from exc
        if event.get("schema") != "ivanka.worker-lease.v1":
            raise Refusal("worker lease journal has wrong schema")
        lease = event.get("lease")
        if lease:
            active[lease] = event.get("state") == "active"
    return [lease for lease, is_active in active.items() if is_active]


def verify_stop_boundary(
    token: str, *,
    lock_path: pathlib.Path = GLOBAL_LOCK,
    stop_path: pathlib.Path = STOP_FILE,
    journal: pathlib.Path = LEASE_JOURNAL,
    containers: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Require the real shared lock path, an operator STOP window and a clear worker."""
    if lock_path != GLOBAL_LOCK:
        raise Refusal(f"wrong worker lock: {lock_path} != {GLOBAL_LOCK}")
    if not lock_path.exists() or lock_path.is_symlink() or not lock_path.is_file():
        raise Refusal("global worker lock file is missing or not a regular file")
    if not stop_path.exists() or stop_path.is_symlink() or not stop_path.is_file():
        raise Refusal("STOP sentinel missing: no verified between-arm boundary")
    stop_text = stop_path.read_text(errors="replace")
    if not token or token not in stop_text:
        raise Refusal("lock token is not present in the operator STOP sentinel")
    pending = _active_leases(journal)
    if pending:
        raise Refusal(f"worker lease journal not clear: {pending}")
    if containers is None:
        containers = guard.listed_cids(env)
    if containers:
        raise Refusal(f"container(s) still present: {containers}")
    return {
        "lock": str(lock_path), "stop": str(stop_path),
        "stop_text": stop_text.strip(), "active_leases": pending,
        "containers": containers,
    }


@contextlib.contextmanager
def shared_worker_lock(token: str, output_root: pathlib.Path) -> Iterator[dict[str, Any]]:
    """Hold the real PX flock across both arms; never create a private lock."""
    boundary = verify_stop_boundary(token)
    try:
        descriptor = os.open(GLOBAL_LOCK, os.O_RDWR)  # no O_CREAT
    except OSError as exc:
        raise Refusal("cannot open the real global worker lock") from exc
    journal = output_root / "lock_journal.jsonl"
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("global worker lock is held; fail closed") from exc
        # Re-check the boundary while holding the lock.
        boundary = verify_stop_boundary(token)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": "ACQUIRE", "at": time.time(), "token": token,
                "pid": os.getpid(), "lock": str(GLOBAL_LOCK),
            }, sort_keys=True) + "\n")
        try:
            yield boundary
        finally:
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "event": "RELEASE", "at": time.time(), "token": token,
                    "pid": os.getpid(), "lock": str(GLOBAL_LOCK),
                }, sort_keys=True) + "\n")
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _resolve_for_teardown(name: str, env: dict[str, str]) -> dict[str, Any]:
    try:
        cid = guard.command(
            ["podman", "inspect", "--format", "{{.Id}}", name], env
        )
        return guard.stop_cid(cid, env)
    except (guard.GuardExceeded, subprocess.SubprocessError):
        names = guard.command(
            ["podman", "ps", "-a", "--format", "{{.Names}}"], env
        ).splitlines()
        if name in names:
            raise Refusal("container present but exact CID unavailable; fail closed")
        return {
            "cid": None, "container_removed": False,
            "fresh_absence_check": True, "kernel_enforcement": False,
        }


def run_arm(arm: str, results: pathlib.Path) -> dict[str, Any]:
    name = f"ivanka-p1-matched-{CASE}-{arm}"
    command_line = argv_for(IMAGES[arm], results, arm)
    (results / "argv.json").write_text(json.dumps(command_line, indent=2, sort_keys=True))
    env = os.environ.copy()
    started = time.time()
    host_before = _host_state()
    deadline = time.monotonic() + WALL_DEADLINE
    log_path = results / "podman.log"
    process: subprocess.Popen[bytes] | None = None
    bound: dict[str, Any] | None = None
    peak: int | None = None
    teardown: dict[str, Any] | None = None
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(command_line, stdout=log, stderr=subprocess.STDOUT)
        bind_until = min(deadline, time.monotonic() + BIND_WINDOW)
        while time.monotonic() < bind_until:
            try:
                bound = guard.bind_by_name(name, env)
                break
            except guard.GuardExceeded as exc:
                if exc.reason != "binding_unavailable":
                    raise
            except subprocess.SubprocessError:
                pass
            time.sleep(0.25)
        if bound is None:
            raise guard.GuardExceeded("binding_unavailable")
        peak = guard.watch(
            bound, limit=guard.RSS_LIMIT, deadline=deadline,
            running=lambda: process.poll() is None,
        )
        try:
            status = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise guard.GuardExceeded("wall_limit") from exc
        if status != 0:
            raise Refusal(f"{arm} MiCall launcher exited {status}")
        timing = read_timing(results / "timing.json")
        stages = parse_stages(log_path.read_text(errors="replace"))
        hashes = {
            item: sha256(results / item)
            for item in ARTIFACTS if (results / item).is_file()
        }
    finally:
        try:
            teardown = (
                guard.stop_cid(bound["cid"], env) if bound is not None
                else _resolve_for_teardown(name, env)
            )
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
    return {
        "arm": arm,
        "image": IMAGES[arm],
        "wall_seconds": round(time.time() - started, 3),
        "deadline_seconds": WALL_DEADLINE,
        "timing": timing,
        "stages": stages,
        "artifact_sha256": hashes,
        "guard": {
            "peak_rss_bytes": peak, "rss_limit_bytes": guard.RSS_LIMIT,
            "enforcement": "userspace_observed", "kernel_enforcement": False,
            "teardown": teardown,
        },
        "host_before": host_before,
        "host_after": _host_state(),
        "exit_code": status,
    }


def plan() -> dict[str, Any]:
    template = argv_for(IMAGES["frozen_ivanka"], pathlib.Path("/OUT/FROZEN"), "frozen_ivanka")
    candidate = argv_for(IMAGES["candidate_ivanka"], pathlib.Path("/OUT/CANDIDATE"), "candidate_ivanka")
    return {
        "schema": SCHEMA,
        "case": CASE,
        "read_sha256": READ_SHA256,
        "timer_sha256": TIMER_SHA256,
        "arms": {"frozen_ivanka": template, "candidate_ivanka": candidate},
        "invariants": {
            "cpus": CPUS,
            "memory_bytes": MEMORY,
            "timeout_seconds": TIMEOUT,
            "stop_timeout_seconds": STOP_TIMEOUT,
            "same_read_mount": True,
            "same_timer_mount": True,
            "same_micall_command": True,
            "only_image_result_dir_and_unique_container_name_differ": True,
            "same_host_and_back_to_back_window": True,
            "existing_benchmark_artifacts_read_only": True,
            "real_global_worker_lock": str(GLOBAL_LOCK),
            "verified_stop_boundary": str(STOP_FILE),
            "exact_cid_fail_closed_rss_guard": True,
            "one_wall_deadline_seconds": WALL_DEADLINE,
            "exact_cid_teardown_in_finally": True,
            "no_truth_or_reference_access": True,
            "qualification_impact": "none_diagnostic_only",
            "drift_conclusion": "strong_evidence_not_causal_proof",
        },
    }


def execute(output_root: pathlib.Path, lock_token: str) -> dict[str, Any]:
    pins = check_inputs()
    root = check_output_root(str(output_root))
    report_path = root / "matched_timing_report.json"
    arms: dict[str, dict[str, Any]] = {}
    try:
        with shared_worker_lock(lock_token, root) as boundary:
            for arm in ("frozen_ivanka", "candidate_ivanka"):
                # STOP is a between-arm boundary: re-verify before dispatch.
                verify_stop_boundary(lock_token)
                arms[arm] = run_arm(arm, root / arm)
    except (guard.GuardExceeded, Refusal) as exc:
        reason = exc.reason if isinstance(exc, guard.GuardExceeded) else str(exc)
        report = {
            "schema": SCHEMA, "case": CASE, "pins": pins,
            "status": "failed_closed", "reason": reason,
            "arms": arms, "boundary": boundary if "boundary" in locals() else None,
            "formal_qualification": False,
            "metric_or_frozen_artifact_change": False,
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
        raise
    frozen, candidate = arms["frozen_ivanka"], arms["candidate_ivanka"]
    identical = {
        item: frozen["artifact_sha256"].get(item) == candidate["artifact_sha256"].get(item)
        for item in ARTIFACTS
    }
    report = {
        "schema": SCHEMA, "case": CASE, "pins": pins,
        "status": "measured", "arms": arms,
        "wall_ratio_candidate_over_frozen": round(
            candidate["wall_seconds"] / frozen["wall_seconds"], 4),
        "stage_ratio_candidate_over_frozen": round(
            candidate["stages"]["remap_to_sam2aln_seconds"]
            / frozen["stages"]["remap_to_sam2aln_seconds"], 4),
        "artifact_byte_identical": identical,
        "interpretation": "strong_evidence_of_environment_drift_not_causal_proof",
        "formal_qualification": False,
        "metric_or_frozen_artifact_change": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="launch the two guarded arms")
    parser.add_argument("--output-root", default=None, help="fresh diagnostic namespace")
    parser.add_argument("--lock-token", default=None, help="PX/P1 token present in STOP")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2, sort_keys=True))
        return 0
    if not args.output_root:
        raise Refusal("--execute requires a fresh --output-root")
    report = execute(pathlib.Path(args.output_root), args.lock_token or "")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Refusal, guard.GuardExceeded) as error:
        reason = error.reason if isinstance(error, guard.GuardExceeded) else str(error)
        print(f"REFUSED: {reason}", file=sys.stderr)
        sys.exit(2)
