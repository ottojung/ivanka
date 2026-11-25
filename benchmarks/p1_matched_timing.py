#!/usr/bin/env python3
"""Reproducible same-resource confirmatory timing for ultradeep-s009.

Diagnostic only. This module does NOT change any benchmark metric, gate,
qualification verdict, frozen artifact, MiCall source or container image.

It builds one argv template for two arms (frozen Ivanka and the P1 candidate),
 differing ONLY in image digest and result directory. Both arms use:

  --cpus=2 --memory=4000000000 --timeout 2400 --stop-timeout 2
  --network=none --userns=host --pull=never --denovo --keep_scratch
  --all_projects

and the same read-only reads mount, timer mount and in-container timer entry
point. The two arms run back-to-back under one host/time window; per-stage
durations are parsed from each arm's retained MiCall log.

Execution is opt-in and guarded by an explicit PX/P1 lock token. With no
--execute the tool only prints the plan (no subprocess, no file write).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any

SCHEMA = "ivanka.p1.matched-timing.v1"
CASE = "ultradeep-s009"

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
MEMORY = "4000000000"  # 4 GB, matched to the P1 candidate arm
TIMEOUT = "2400"  # 40 m, matched to the P1 candidate arm
STOP_TIMEOUT = "2"

# Existing sealed evidence. The runner must never write under these roots.
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
    """Verify the exact read pair and timer are present and pinned."""
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
    """Reject any output root that could touch sealed evidence."""
    root = pathlib.Path(raw).expanduser().resolve()
    if root == pathlib.Path("/"):
        raise Refusal("output root may not be /")
    for protected in PROTECTED_ROOTS:
        resolved = protected.resolve()
        if root == resolved or resolved in root.parents or root in resolved.parents:
            raise Refusal(f"output root {root} overlaps protected {resolved}")
    if root.exists() and any(root.iterdir()):
        raise Refusal(f"output root {root} already contains files; use a fresh one")
    for name in READ_SHA256:
        if (root / name).exists():
            raise Refusal("output root may not contain read inputs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def argv_for(image: str, results: pathlib.Path, arm: str) -> list[str]:
    """One template; image and result directory are the only differences."""
    return [
        "podman",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--userns=host",
        "--cpus=" + CPUS,
        "--memory=" + MEMORY,
        "--name",
        f"ivanka-p1-matched-{CASE}-{arm}",
        "--timeout",
        TIMEOUT,
        "--stop-timeout",
        STOP_TIMEOUT,
        "-v",
        f"{READS}:/reads:ro",
        "-v",
        f"{results}:/results:rw",
        "-v",
        f"{TIMER}:/ivanka-timer.py:ro",
        "--entrypoint",
        "/opt/venv/bin/python",
        image,
        "/ivanka-timer.py",
        "/results/timing.json",
        "micall",
        "analyze",
        "sample",
        "/reads/R1.fastq.gz",
        "/reads/R2.fastq.gz",
        "/results",
        "--denovo",
        "--keep_scratch",
        "--bad_cycles_csv",
        "/results/bad_cycles.csv",
        "--all_projects",
    ]


def _parse_stamp(text: str) -> float:
    match = STAMP.search(text)
    if not match:
        raise ValueError(f"no MiCall timestamp in {text!r}")
    date, millis = match.group(1).split(",")
    return time.mktime(time.strptime(date, "%Y-%m-%d %H:%M:%S")) + int(millis) / 1000.0


def parse_stages(log: str) -> dict[str, Any]:
    """Parse stage durations from a retained MiCall log, diagnostic only."""
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
        seconds = round(seen[index][1] - seen[index - 1][1], 3)
        # Occurrences of a repeated stage are numbered for a stable record.
        key = name
        suffix = 1
        while key in stages:
            suffix += 1
            key = f"{name}#{suffix}"
        stages[key] = seconds
    remap = next((value for name, value in seen if name == "Running remap"), None)
    first_sam2aln = next(
        (value for name, value in seen if name == "Running sam2aln"), None
    )
    if remap is None or first_sam2aln is None:
        raise ValueError("missing remap or sam2aln marker")
    return {
        "native_assembly_seconds": native[-1] if native else micall_native[-1],
        "micall_assembly_seconds": micall_native[-1],
        "remap_to_sam2aln_seconds": round(first_sam2aln - remap, 3),
        "stages": stages,
        "timestamps": [{"marker": name, "epoch": value} for name, value in seen],
    }


def read_timing(path: pathlib.Path) -> dict[str, Any]:
    record = json.loads(path.read_text())
    if record.get("timing_origin") != "micall_in_container_monotonic_v1":
        raise Refusal(f"unexpected timing origin in {path}")
    if record.get("exit_code") != 0:
        raise Refusal(f"nonzero MiCall exit code in {path}")
    if not isinstance(record.get("seconds"), (int, float)) or record["seconds"] <= 0:
        raise Refusal(f"invalid timing value in {path}")
    return record


def _host_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "loadavg": list(os.getloadavg()),
        "cpu_count": os.cpu_count(),
    }
    quota = pathlib.Path("/sys/fs/cgroup/cpu.max")
    if quota.is_file():
        state["cgroup_cpu_max"] = quota.read_text().strip()
    return state


def _acquire_lock(token: str) -> tuple[pathlib.Path, pathlib.Path]:
    """Require an explicit PX/P1 coordination token and create a fresh lease."""
    if not token or len(token) < 12:
        raise Refusal("--lock-token must name the coordinating PX/P1 owner")
    lock = pathlib.Path(
        os.environ.get(
            "P1_RUNTIME_LOCK_PATH", "/tmp/opencode/p1-runtime-shared.lock"
        )
    )
    journal = lock.with_suffix(".journal")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise Refusal(f"shared runtime lock is held: {lock}") from exc
    with handle:
        handle.write(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "case": CASE,
                    "token": token,
                    "pid": os.getpid(),
                    "acquired": time.time(),
                },
                sort_keys=True,
            )
            + "\n"
        )
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(f"ACQUIRE {time.time():.6f} {token}\n")
    return lock, journal


def _release_lock(lock: pathlib.Path, journal: pathlib.Path, token: str) -> None:
    if lock.is_file():
        lock.unlink()
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(f"RELEASE {time.time():.6f} {token}\n")


def run_arm(arm: str, results: pathlib.Path) -> dict[str, Any]:
    """Launch one podman arm and capture only its own fresh result folder."""
    command = argv_for(IMAGES[arm], results, arm)
    (results / "argv.json").write_text(json.dumps(command, indent=2, sort_keys=True))
    start = time.time()
    host_before = _host_state()
    log_path = results / "podman.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            status = process.wait(timeout=int(TIMEOUT) + 120)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["podman", "rm", "-f", f"ivanka-p1-matched-{CASE}-{arm}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            raise Refusal(f"{arm} exceeded hard timeout; container removed")
    wall = round(time.time() - start, 3)
    host_after = _host_state()
    timing = read_timing(results / "timing.json")
    stages = parse_stages(log_path.read_text(errors="replace"))
    hashes = {name: sha256(results / name) for name in ARTIFACTS if (results / name).is_file()}
    return {
        "arm": arm,
        "image": IMAGES[arm],
        "container_wall_seconds": wall,
        "timing": timing,
        "stages": stages,
        "artifact_sha256": hashes,
        "host_before": host_before,
        "host_after": host_after,
        "exit_code": status,
    }


def plan() -> dict[str, Any]:
    """The exact invariant set that --execute will enforce."""
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
            "requires_px_p1_lock_token": True,
            "no_truth_or_reference_access": True,
            "qualification_impact": "none_diagnostic_only",
        },
    }


def execute(output_root: pathlib.Path, lock_token: str) -> dict[str, Any]:
    pins = check_inputs()
    root = check_output_root(str(output_root))
    lock, journal = _acquire_lock(lock_token)
    try:
        arms = {}
        for arm in ("frozen_ivanka", "candidate_ivanka"):
            arms[arm] = run_arm(arm, root / arm)
    finally:
        _release_lock(lock, journal, lock_token)
    frozen = arms["frozen_ivanka"]
    candidate = arms["candidate_ivanka"]
    identical = {
        name: frozen["artifact_sha256"].get(name)
        == candidate["artifact_sha256"].get(name)
        for name in ARTIFACTS
    }
    report = {
        "schema": SCHEMA,
        "case": CASE,
        "pins": pins,
        "arms": arms,
        "wall_ratio_candidate_over_frozen": round(
            candidate["container_wall_seconds"] / frozen["container_wall_seconds"], 4
        ),
        "stage_ratio_candidate_over_frozen": round(
            candidate["stages"]["remap_to_sam2aln_seconds"]
            / frozen["stages"]["remap_to_sam2aln_seconds"],
            4,
        ),
        "artifact_byte_identical": identical,
        "formal_qualification": False,
        "metric_or_frozen_artifact_change": False,
    }
    (root / "matched_timing_report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="launch the two guarded arms")
    parser.add_argument("--output-root", default=None, help="fresh diagnostic namespace")
    parser.add_argument("--lock-token", default=None, help="PX/P1 coordination token")
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
    except Refusal as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        sys.exit(2)
