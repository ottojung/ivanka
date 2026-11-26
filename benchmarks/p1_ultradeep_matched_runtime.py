#!/usr/bin/env python3
"""Plan-only matched-resource alternating timing diagnostic for s006-s009.

Diagnostic only: no OCI build/run, no deployment, no benchmark metric, gate or
qualification change. Historical receipts are read-only and SHA-verified. Host
evidence is aggregate-only; no per-process argument data is read or recorded.
Guarded execution stays blocked while the build-admission and natural-exit
dependencies (PR535/PR536) are pending, so this module only emits a plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))

SCHEMA = "ivanka.p1.ultradeep-matched-runtime.plan.v1"
RECEIPT_SCHEMA = "ivanka.ultradeep-runtime-diagnostic.v1"
RECEIPT_SHA256 = "7d0726a5cf6d6f9bb7a42689402633fe44ad5c30621fa7881b0862fe6b262e5c"
CASES = ("ultradeep-s006", "ultradeep-s007", "ultradeep-s008", "ultradeep-s009")
CANDIDATE_COMMIT = "12d8c72f01f305b7f81db26193ec5fc213ba55bf"
FROZEN_IMAGE = "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"
CANDIDATE_IMAGE = "6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971"
TIMER_SHA256 = "c5baab15b8c54f27b5cfbaf459f8647707e1e9618577b803ee3440e3e661eb4e"
READS_ROOT = pathlib.Path("/workspace/ivanka-synthetic-abundance15-464-20261117")
TIMER_PATH = pathlib.Path(
    "/workspace/micall-frozen-seven-20261117/ivanka-physical-source/"
    "benchmarks/inside_container_timing.py"
)
READ_SHA256 = {
    "ultradeep-s006": {
        "R1.fastq.gz": "8c056bd05e59000e3da2adbfcce0abe8c1f43007de6d861fba64e7826cbf10c4",
        "R2.fastq.gz": "77476a42721b315984f5b9c886bbb5bb3bde240559ff8de1da97cf1522416a99",
    },
    "ultradeep-s007": {
        "R1.fastq.gz": "fcd226e03a03cb77e4f5703c599d0e62709494d2a1e45da2e52b2b277881ad5f",
        "R2.fastq.gz": "2f739fb297fd1b37be87f6c11c0079b0dd3ef8b92e37ab5962af0cf4a878de4d",
    },
    "ultradeep-s008": {
        "R1.fastq.gz": "2670192d0bd932f24bef76df1b09d877cd622c700fd27cea408fe66b8224abbf",
        "R2.fastq.gz": "40ddfe3f831da9537295b9290f2dc37fc64a155ccccb287b239d5d2ab8d9a0d8",
    },
    "ultradeep-s009": {
        "R1.fastq.gz": "56ce9217976f60eacd2a9376f2198fa79c4cecc5cb29e19c0ebe62f2c741f5d8",
        "R2.fastq.gz": "2a72ccbde6261c28a239a439b4740eb1c5a2f879bb198f62f1440753b9a03025",
    },
}
CONSTRAINTS = {
    "cpus": "2",
    "memory": "4000000000",
    "timeout": "2400",
    "stop_timeout": "2",
    "pull": "never",
    "network": "none",
    "micall_flags": ["--denovo", "--keep_scratch", "--all_projects"],
}
DEPENDENCIES = {
    "PR535": "433e4ea8630018b2549e581a5c36ca9aed58bdb4",
    "PR536": "6e6886a824a7cb0f1b812f1c24c233f8100a9d8b",
}
PROTECTED_ROOTS = (
    pathlib.Path("/workspace/micall-frozen-seven-20261117"),
    pathlib.Path("/workspace/ivanka-p1-full464-12d8c72-20261124"),
    READS_ROOT,
)


class Refusal(Exception):
    """A safety invariant failed; no arm may be launched."""


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_receipt(path: pathlib.Path) -> dict[str, Any]:
    """Read the immutable PR539 residual receipt or refuse."""
    if sha256(path) != RECEIPT_SHA256:
        raise Refusal("receipt SHA-256 mismatch")
    report = json.loads(path.read_text())
    if report.get("schema") != RECEIPT_SCHEMA or report.get("case_count") != 16:
        raise Refusal("unexpected receipt schema or case count")
    rows = {row["case"]: row for row in report.get("cases", [])}
    if set(CASES) - set(rows):
        raise Refusal("receipt missing a selected ultradeep case")
    for case in CASES:
        row = rows[case]
        if not row.get("ordered_unstitched_sequences_identical") or not row.get(
            "conseq_csv_bytes_identical"
        ):
            raise Refusal("receipt output identity not established for " + case)
        for key in ("candidate_seconds", "frozen_seconds"):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Refusal("invalid historical timing")
            if not math.isfinite(value) or not 0 < value <= int(CONSTRAINTS["timeout"]):
                raise Refusal("historical timing outside deadline")
    return report


def pinned_inputs(verify_files: bool, reads_root: pathlib.Path = READS_ROOT) -> dict[str, Any]:
    """Return pins; when asked, verify file bytes without writing anything."""
    if not verify_files:
        return {"reads": READ_SHA256, "timer_sha256": TIMER_SHA256, "verified": False}
    for case, names in READ_SHA256.items():
        for name, expected in names.items():
            path = reads_root / case / "reads" / name
            if not path.is_file() or sha256(path) != expected:
                raise Refusal("read pin mismatch for " + case + "/" + name)
    if not TIMER_PATH.is_file() or sha256(TIMER_PATH) != TIMER_SHA256:
        raise Refusal("timer pin mismatch")
    return {"reads": READ_SHA256, "timer_sha256": TIMER_SHA256, "verified": True}


def alternating_schedule(cases: tuple[str, ...] = CASES) -> list[dict[str, str]]:
    """Deterministic AB/BA alternation; no outcome-dependent ordering."""
    steps = []
    for index, case in enumerate(cases):
        order = ("frozen", "candidate") if index % 2 == 0 else ("candidate", "frozen")
        for arm in order:
            steps.append({"case": case, "arm": arm})
    return steps


def argv_for(step: dict[str, str], output_root: pathlib.Path) -> list[str]:
    """One template per arm; only image, results directory and name differ."""
    case, arm = step["case"], step["arm"]
    image = FROZEN_IMAGE if arm == "frozen" else CANDIDATE_IMAGE
    reads = READS_ROOT / case / "reads"
    results = output_root / case / arm
    return [
        "podman", "run", "--rm", "--pull=" + CONSTRAINTS["pull"],
        "--network=" + CONSTRAINTS["network"], "--userns=host",
        "--cpus=" + CONSTRAINTS["cpus"], "--memory=" + CONSTRAINTS["memory"],
        "--name", "p1-ultradeep-matched-" + case + "-" + arm,
        "--timeout", CONSTRAINTS["timeout"], "--stop-timeout", CONSTRAINTS["stop_timeout"],
        "-v", str(reads) + ":/reads:ro",
        "-v", str(results) + ":/results:rw",
        "-v", str(TIMER_PATH) + ":/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
    ] + CONSTRAINTS["micall_flags"]


def effective_cpus(cpu_max_text: str) -> float | None:
    """Translate cgroup v2 cpu.max into effective CPU count (None = unlimited)."""
    parts = cpu_max_text.split()
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        raise ValueError("invalid cpu.max")
    if parts[0] == "max":
        return None
    if not parts[0].isdigit():
        raise ValueError("invalid cpu.max quota")
    return int(parts[0]) / int(parts[1])


def host_evidence(
    cgroup_root: pathlib.Path = pathlib.Path("/sys/fs/cgroup"),
    proc_root: pathlib.Path = pathlib.Path("/proc"),
) -> dict[str, Any]:
    """Aggregate pressure/load/CPU-allocation snapshot, never per-process data."""
    evidence: dict[str, Any] = {"loadavg": None, "cpu_max": None,
                                 "effective_cpus": None, "cpuset_effective": None,
                                 "cpu_stat": {}, "memory_current": None}
    loadavg = proc_root / "loadavg"
    if loadavg.is_file():
        fields = loadavg.read_text().split()
        if len(fields) >= 3:
            evidence["loadavg"] = [float(value) for value in fields[:3]]
    quota = cgroup_root / "cpu.max"
    if quota.is_file():
        evidence["cpu_max"] = quota.read_text().strip()
        evidence["effective_cpus"] = effective_cpus(evidence["cpu_max"])
    cpuset = cgroup_root / "cpuset.cpus.effective"
    if cpuset.is_file():
        evidence["cpuset_effective"] = cpuset.read_text().strip()
    stat = cgroup_root / "cpu.stat"
    if stat.is_file():
        for line in stat.read_text().splitlines():
            name, _, value = line.partition(" ")
            if value.strip().isdigit():
                evidence["cpu_stat"][name] = int(value)
    memory = cgroup_root / "memory.current"
    if memory.is_file() and memory.read_text().strip().isdigit():
        evidence["memory_current"] = int(memory.read_text().strip())
    return evidence


def readiness(attestation: pathlib.Path | None) -> dict[str, Any]:
    """Guard dependencies are pending until both exact heads are attested merged."""
    blocked: list[str] = []
    if attestation is None or not attestation.is_file():
        return {"ready": False, "blocked_by": sorted(DEPENDENCIES)}
    record = json.loads(attestation.read_text())
    for name, head in DEPENDENCIES.items():
        state = record.get(name, {})
        if state.get("state") != "merged" or state.get("head") != head:
            blocked.append(name)
    return {"ready": not blocked, "blocked_by": sorted(set(blocked))}


def check_output_root(raw: str | pathlib.Path) -> pathlib.Path:
    """Evidence may only be written to a fresh directory outside sealed roots."""
    root = pathlib.Path(raw).expanduser().resolve()
    if root == pathlib.Path("/"):
        raise Refusal("output root may not be /")
    for protected in PROTECTED_ROOTS:
        if root == protected or protected in root.parents or root in protected.parents:
            raise Refusal("output root overlaps a protected root")
    if root.exists() and any(root.iterdir()):
        raise Refusal("output root is not fresh")
    return root


def arm_evidence_record(
    step: dict[str, str], before: dict[str, Any], after: dict[str, Any],
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Durable per-arm record: aggregate host pressure plus matched timing."""
    return {
        "schema": "ivanka.p1.ultradeep.arm-evidence.v1",
        "case": step["case"], "arm": step["arm"],
        "image": FROZEN_IMAGE if step["arm"] == "frozen" else CANDIDATE_IMAGE,
        "candidate_commit": CANDIDATE_COMMIT if step["arm"] == "candidate" else None,
        "host_before": before, "host_after": after,
        "timing_origin": timing.get("timing_origin"),
        "wall_seconds": timing.get("seconds"),
        "exit_code": timing.get("exit_code"),
        "constraints": CONSTRAINTS,
        "privacy": "aggregate_only_no_process_arguments",
        "formal_qualification": False,
    }


def write_arm_evidence(root: pathlib.Path, record: dict[str, Any]) -> pathlib.Path:
    """Used only by a future guarded executor; never by plan generation."""
    directory = root / record["case"] / record["arm"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "host-evidence.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def build_plan(
    receipt_path: pathlib.Path,
    output_root: pathlib.Path,
    *,
    verify_files: bool = False,
    attestation: pathlib.Path | None = None,
) -> dict[str, Any]:
    receipt = load_receipt(receipt_path)
    gate = readiness(attestation)
    steps = alternating_schedule()
    rows = {row["case"]: row for row in receipt["cases"]}
    return {
        "schema": SCHEMA,
        "candidate_commit": CANDIDATE_COMMIT,
        "images": {"frozen": FROZEN_IMAGE, "candidate": CANDIDATE_IMAGE},
        "constraints": CONSTRAINTS,
        "inputs": pinned_inputs(verify_files),
        "output_root": str(output_root),
        "schedule": [
            {**step, "argv": argv_for(step, output_root)} for step in steps
        ],
        "historical_receipt": {
            "sha256": RECEIPT_SHA256,
            "cases": {
                case: {
                    "candidate_seconds": rows[case]["candidate_seconds"],
                    "frozen_seconds": rows[case]["frozen_seconds"],
                    "native_delta_seconds": rows[case]["native_delta_seconds"],
                    "unattributed_delta_seconds": rows[case]["unattributed_delta_seconds"],
                }
                for case in CASES
            },
        },
        "host_evidence": host_evidence(),
        "dependencies": gate,
        "execution": "blocked",
        "scientific_gates_changed": False,
        "formal_qualification": False,
        "strong_evidence_not_causal_proof": True,
        "privacy": "aggregate_only_no_process_arguments",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt", type=pathlib.Path,
        default=pathlib.Path(__file__).parent.parent
        / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json",
    )
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--attestation", type=pathlib.Path)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--emit-plan", type=pathlib.Path)
    args = parser.parse_args()
    plan = build_plan(
        args.receipt, args.output_root,
        verify_files=args.verify_files, attestation=args.attestation,
    )
    text = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.emit_plan is not None:
        target = check_output_root(args.emit_plan.parent)
        if args.emit_plan.name != "plan.json":
            raise Refusal("plan file must be plan.json in a fresh root")
        (target / "plan.json").write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
