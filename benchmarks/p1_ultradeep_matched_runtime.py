#!/usr/bin/env python3
"""Plan-only matched-resource alternating timing diagnostic for s006-s009.

Diagnostic only: no OCI build/run, no deployment, no benchmark metric, gate or
qualification change. Historical receipts are read-only and SHA-verified. Host
evidence is aggregate-only; no per-process argument data is read or recorded.
There is deliberately no execution mode: readiness can only *describe* whether
a future guarded run may be considered, never authorize one by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))

SCHEMA = "ivanka.p1.ultradeep-matched-runtime.plan.v1"
ATTESTATION_SCHEMA = "ivanka.p1.guard-deployment-attestation.v1"
RECEIPT_SCHEMA = "ivanka.ultradeep-runtime-diagnostic.v1"
RECEIPT_SHA256 = "7d0726a5cf6d6f9bb7a42689402633fe44ad5c30621fa7881b0862fe6b262e5c"
CASES = ("ultradeep-s006", "ultradeep-s007", "ultradeep-s008", "ultradeep-s009")
# Ordinary controls: one typical ultradeep (small historical unattributed delta,
# identical outputs) and one ordinary clonal (near-zero historical delta,
# identical outputs). Selection is documented, not outcome-dependent.
CONTROL_CASES = ("ultradeep-s002", "clonal-s015")
ALL_CASES = CASES + CONTROL_CASES
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
    "ultradeep-s002": {
        "R1.fastq.gz": "94fdc0312526679a517f3221c4a4db9a9d292fd39676789af01df654aa36c755",
        "R2.fastq.gz": "9197a88487c770556145e421a6f141cddb40c6d343af5dd36fbab48d0e7386e4",
    },
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
    "clonal-s015": {
        "R1.fastq.gz": "9e3e884062d799ca550afc65e4825f35c5b0a5cf26e602b94c3b2e2081722812",
        "R2.fastq.gz": "6968c00d05c3d6763e25413bb80be4749b6142beb58260cbf4b312eddf8d20d3",
    },
}
# Historical control timings from the pinned full-stage-intervals diagnostic.
# These are retained retrospective measurements, never new execution.
FULL_STAGE_INTERVALS_SHA256 = "62ac208258e8427730ab08ff806811c258b08f073c5bea1927bbe300070059ee"
CONTROL_HISTORICAL = {
    "ultradeep-s002": {
        "source": "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json",
        "source_sha256": RECEIPT_SHA256,
        "candidate_seconds": 186.855614907,
        "frozen_seconds": 139.86058835,
        "ordered_unstitched_sequences_identical": True,
        "conseq_csv_bytes_identical": True,
    },
    "clonal-s015": {
        "source": "docs/bench/diagnostics/p1-full-stage-intervals-20261127.json",
        "source_sha256": FULL_STAGE_INTERVALS_SHA256,
        "candidate_seconds": 74.678916762,
        "frozen_seconds": 76.018442715,
        "ordered_unstitched_sequences_identical": True,
        "conseq_csv_bytes_identical": True,
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
# Exact merged SOURCE identities. A merge is a source fact only: it never
# proves which guard PX and the independent watchdog actually run. Deployment
# is pinned separately below and describes the older live guard stack.
SOURCE_PINS = {
    "PR535": {
        "state": "merged",
        "head": "39317f021f4e5c00f5da859bcdcf755de4c6d353",
        "merge_commit": "165a86b38c0bc29b4f8e0281a39ca59b909a6563",
    },
    "PR536": {
        "state": "merged",
        "head": "6e6886a824a7cb0f1b812f1c24c233f8100a9d8b",
        "merge_commit": "091f56275ae823cb3291b81dbdf016fcf16c3ea0",
    },
}
# Retained for callers that only need the exact source heads (never deployment).
DEPENDENCIES = {name: pin["head"] for name, pin in SOURCE_PINS.items()}

# Reviewed actual deployed roots, read from live s6 run scripts and staged
# trees. Guard source/root and service pins are separate immutable values and
# must be attested separately. Digests are recomputed from the deployed tree.
DEPLOYED_PINS = {
    "guard_source_head": "165a86b38c0bc29b4f8e0281a39ca59b909a6563",
    "deployed_root_head": "165a86b38c0bc29b4f8e0281a39ca59b909a6563",
    "px_service_head": "b8720600c9f10e71472b2b55210badeabc257a81",
    "watchdog_service_head": "165a86b38c0bc29b4f8e0281a39ca59b909a6563",
    "guard_sha256": {
        "natural_exit_sha256":
            "f7f6028273a5d7775b8d4ca6139e9659ca475a0aa36a3d12b1a736e429202cd6",
        "watch_sha256":
            "07356fc4b29e1e6bc5b11659048bc5437a70037a29dde197dd795540fd66da96",
        "monitor_sha256":
            "b0bbefa221ff092acf33021b0203f2b07a912c250fc0893e8fdd59dad642293c",
        "p1_helper_sha256":
            "b950ff947da8144271d8f4f0064fe72b4d6b1a492591e36610b942a553f21a27",
        "p1_harness_sha256":
            "c193ca79b23fc6f2190b92ae7ce70d46de582a3fd71d9c17d09c6b6704d185fb",
    },
}
KERNEL_QUOTA_ORIGINS = ("kernel_cgroup_v2_cpu_max", "kernel_cgroup_v1_cpu_cfs")
COMPARABILITY = {
    "required_container_cpu_max": "200000 100000",
    "required_container_effective_cpus": 2.0,
    "min_effective_host_cpus": 2.0,
    "max_loadavg_per_cpu": 1.0,
    "max_throttle_ratio": 0.05,
    "max_host_load_ratio_between_arms": 1.5,
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


def load_receipt(path: pathlib.Path, cases: tuple[str, ...] = CASES) -> dict[str, Any]:
    """Read the immutable PR539 residual receipt or refuse."""
    if sha256(path) != RECEIPT_SHA256:
        raise Refusal("receipt SHA-256 mismatch")
    report = json.loads(path.read_text())
    if report.get("schema") != RECEIPT_SCHEMA or report.get("case_count") != 16:
        raise Refusal("unexpected receipt schema or case count")
    rows = {row["case"]: row for row in report.get("cases", [])}
    missing = set(cases) - set(rows)
    if missing:
        raise Refusal("receipt missing selected case: " + ", ".join(sorted(missing)))
    for case in cases:
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


def pinned_inputs(
    verify_files: bool,
    reads_root: pathlib.Path = READS_ROOT,
    cases: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return pins; when asked, verify file bytes without writing anything."""
    selected = tuple(cases) if cases is not None else tuple(READ_SHA256)
    unknown = [c for c in selected if c not in READ_SHA256]
    if unknown:
        raise Refusal("unknown case pins: " + ", ".join(sorted(unknown)))
    reads = {case: READ_SHA256[case] for case in selected}
    if not verify_files:
        return {"reads": reads, "timer_sha256": TIMER_SHA256, "verified": False}
    for case in selected:
        for name, expected in READ_SHA256[case].items():
            path = reads_root / case / "reads" / name
            if not path.is_file() or sha256(path) != expected:
                raise Refusal("read pin mismatch for " + case + "/" + name)
    if not TIMER_PATH.is_file() or sha256(TIMER_PATH) != TIMER_SHA256:
        raise Refusal("timer pin mismatch")
    return {"reads": reads, "timer_sha256": TIMER_SHA256, "verified": True}


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


def cpuset_count(text: Any) -> int | None:
    """Count CPUs in a cpuset list such as '0-31' or '0,2-3'; None if malformed."""
    if not isinstance(text, str) or not text.strip():
        return None
    total = 0
    for part in text.split(","):
        part = part.strip()
        if not part:
            return None
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2 or not all(bound.isdigit() for bound in bounds):
                return None
            low, high = int(bounds[0]), int(bounds[1])
            if high < low:
                return None
            total += high - low + 1
        elif part.isdigit():
            total += 1
        else:
            return None
    return total or None


def host_cpu_capacity(host: dict[str, Any]) -> float | None:
    """Host CPUs actually available: cpu.max quota, else the effective cpuset."""
    quota = host.get("effective_cpus")
    if isinstance(quota, (int, float)) and not isinstance(quota, bool) and quota > 0:
        return float(quota)
    return cpuset_count(host.get("cpuset_effective"))


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


def contention_check(host: dict[str, Any]) -> dict[str, Any]:
    """Deterministic abort rule for one aggregate host snapshot."""
    reasons: list[str] = []
    load = host.get("loadavg") if isinstance(host, dict) else None
    if (not isinstance(load, list) or not load
            or isinstance(load[0], bool) or not isinstance(load[0], (int, float))):
        reasons.append("missing loadavg")
    capacity = host_cpu_capacity(host) if isinstance(host, dict) else None
    if capacity is None or capacity < COMPARABILITY["min_effective_host_cpus"]:
        reasons.append("insufficient host CPU capacity")
    load_per_cpu = None
    if not reasons:
        load_per_cpu = float(load[0]) / capacity
        if load_per_cpu > COMPARABILITY["max_loadavg_per_cpu"]:
            reasons.append("loadavg per CPU above threshold")
    stat = host.get("cpu_stat") if isinstance(host, dict) else None
    if not isinstance(stat, dict):
        reasons.append("missing cpu.stat")
    else:
        periods, throttled = stat.get("nr_periods"), stat.get("nr_throttled")
        if not isinstance(periods, int) or isinstance(periods, bool) or periods <= 0:
            reasons.append("missing nr_periods")
        elif not isinstance(throttled, int) or isinstance(throttled, bool):
            reasons.append("missing nr_throttled")
        elif throttled / periods > COMPARABILITY["max_throttle_ratio"]:
            reasons.append("cpu throttling above threshold")
    return {"abort": bool(reasons), "reasons": reasons,
            "capacity": capacity, "loadavg_per_cpu": load_per_cpu}


def readiness(attestation: pathlib.Path | None) -> dict[str, Any]:
    """Describe whether an exact-identity guard may be considered.

    Source pins and deployment pins are deliberately separate. Every dependency
    must be attested at its exact merged source head and merge commit, while the
    deployed guard identity must match the reviewed actual deployed roots and
    guard file digests. A merge record is not a deployment and must never be
    reported as ready. Readiness requires exact deployed guard/root/service pins,
    clean tree, fresh watchdog, clear lease, attested idle boundary, and explicit
    attestation metadata. Even a ready-shaped record leaves execution='blocked'
    in the plan; only the explicit executor path can run arms.

    A cutover may only be recognised by a reviewed change to these exact pins
    plus a fresh live attestation of the deployed stack. Attestation text alone
    cannot rebind the deployed truth, and this function never deletes or relaxes
    a guard block to make a run possible.
    """
    all_blocked = sorted(SOURCE_PINS)
    if attestation is None or not attestation.is_file():
        return {"ready": False, "blocked_by": all_blocked,
                "reasons": ["deployment attestation file missing"]}
    try:
        record = json.loads(attestation.read_text())
    except (OSError, ValueError) as exc:
        return {"ready": False, "blocked_by": all_blocked,
                "reasons": ["deployment attestation unreadable: " + type(exc).__name__]}
    if not isinstance(record, dict) or record.get("schema") != ATTESTATION_SCHEMA:
        return {"ready": False, "blocked_by": all_blocked,
                "reasons": ["unexpected deployment attestation schema"]}

    blocked: list[str] = []
    reasons: list[str] = []
    for name, pin in SOURCE_PINS.items():
        state = record.get(name)
        if not isinstance(state, dict) or state.get("state") != pin["state"]:
            blocked.append(name)
            reasons.append(name + " source not attested as merged")
            continue
        if state.get("head") != pin["head"]:
            blocked.append(name)
            reasons.append(name + " merged source head mismatch")
        if state.get("merge_commit") != pin["merge_commit"]:
            blocked.append(name)
            reasons.append(name + " merge commit mismatch")

    deployed = record.get("deployed_sources") if isinstance(
        record.get("deployed_sources"), dict) else {}
    # Source merge facts and deployed guard identity are separate. The deployed
    # guard identity below is authoritative; deployed_sources must be honest.
    for name in SOURCE_PINS:
        value = deployed.get(name, False)
        if not isinstance(value, bool):
            blocked.append(name)
            reasons.append(name + " deployed state not boolean")
    if deployed.get("PR535") is not True:
        blocked.append("PR535")
        reasons.append("PR535 deployed truth not attested")
    if "PR536" in deployed and not isinstance(deployed.get("PR536"), bool):
        blocked.append("PR536")
        reasons.append("PR536 deployed state not boolean")

    guard = record.get("deployed_guard")
    if not isinstance(guard, dict):
        blocked.append("deployed_guard")
        reasons.append("deployed guard identity missing")
    else:
        checks = (
            ("source_head", DEPLOYED_PINS["guard_source_head"],
             "reviewed guard source pin mismatch"),
            ("root_head", DEPLOYED_PINS["deployed_root_head"],
             "deployed guard root HEAD mismatch"),
            ("px_service_head", DEPLOYED_PINS["px_service_head"],
             "PX service pin mismatch"),
            ("watchdog_service_head", DEPLOYED_PINS["watchdog_service_head"],
             "watchdog service pin mismatch"),
            ("guard_sha256", DEPLOYED_PINS["guard_sha256"],
             "guard file digest mismatch"),
            ("tree_clean", True, "deployed guard tree not clean"),
            ("watchdog_alive_fresh", True, "watchdog ALIVE not fresh"),
            ("lease_clear", True, "shared lease not clear"),
            ("idle_boundary_attested", True, "idle boundary not attested"),
        )
        for key, expected, reason in checks:
            if guard.get(key) != expected:
                blocked.append("deployed_guard")
                reasons.append(reason)
    for key in ("attested_by", "attested_at_utc"):
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            blocked.append("attestation")
            reasons.append(key + " missing")
    return {"ready": not blocked and not reasons,
            "blocked_by": sorted(set(blocked)), "reasons": reasons}


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


def stage_timing_from_log(
    log_text: str,
    official_seconds: float | int | None,
) -> dict[str, Any] | None:
    """Parse MiCall stage intervals from a retained log; fail closed on bad shape."""
    if not isinstance(log_text, str) or not log_text.strip():
        return None
    if (isinstance(official_seconds, bool)
            or not isinstance(official_seconds, (int, float))
            or not math.isfinite(official_seconds) or official_seconds <= 0):
        return None
    try:
        from px_stage_interval_diagnostic import intervals
        return intervals(log_text, float(official_seconds))
    except Exception:
        return None


def arm_evidence_record(
    step: dict[str, str], before: dict[str, Any], after: dict[str, Any],
    timing: dict[str, Any], *, sampled_rss_bytes: int | None = None,
    container_cpu_max: str | None = None,
    requested_cpu_max: str | None = None,
    observed_cpu_quota: dict[str, Any] | None = None,
    stage_timing: dict[str, Any] | None = None,
    log_sha256: str | None = None,
) -> dict[str, Any]:
    """Durable per-arm record: matched timing, sampled RSS and kernel quota.

    A requested or configured quota is preserved as a claim only. The
    comparability decision uses the kernel cgroup value observed for the exact
    bound CID/PID during the supervised arm.
    """
    rss_ok = (isinstance(sampled_rss_bytes, int)
              and not isinstance(sampled_rss_bytes, bool) and sampled_rss_bytes > 0)
    requested = requested_cpu_max if isinstance(requested_cpu_max, str) else container_cpu_max
    observed = observed_cpu_quota if isinstance(observed_cpu_quota, dict) else None
    observed_value = observed.get("value") if observed else None
    origin = observed.get("origin") if observed else None
    quota_effective = None
    if isinstance(observed_value, str):
        try:
            quota_effective = effective_cpus(observed_value)
        except ValueError:
            quota_effective = None
    quota_complete = (
        requested == COMPARABILITY["required_container_cpu_max"]
        and quota_effective == COMPARABILITY["required_container_effective_cpus"]
        and origin in KERNEL_QUOTA_ORIGINS)
    record = {
        "schema": "ivanka.p1.ultradeep.arm-evidence.v1",
        "case": step["case"], "arm": step["arm"],
        "image": FROZEN_IMAGE if step["arm"] == "frozen" else CANDIDATE_IMAGE,
        "candidate_commit": CANDIDATE_COMMIT if step["arm"] == "candidate" else None,
        "host_before": before, "host_after": after,
        "timing_origin": timing.get("timing_origin"),
        "wall_seconds": timing.get("seconds"),
        "exit_code": timing.get("exit_code"),
        "sampled_peak_rss_bytes": sampled_rss_bytes if rss_ok else None,
        "rss_evidence_complete": rss_ok,
        "cpu_quota": {
            "host_cpu_max": before.get("cpu_max"),
            "requested_container_cpu_max": requested,
            "container_cpu_max": requested,
            "observed_container_cpu_max": observed_value,
            "observed_cpu_max_origin": origin,
            "observed_pid": observed.get("pid") if observed else None,
            "observed_cgroup": observed.get("cgroup") if observed else None,
            "observed_raw": observed.get("raw") if observed else None,
            "container_effective_cpus": quota_effective,
            "memory_limit_bytes": int(CONSTRAINTS["memory"]),
        },
        "cpu_quota_complete": quota_complete,
        "rss_enforcement": "sampled_userspace_observed",
        "kernel_enforcement": False,
        "constraints": CONSTRAINTS,
        "privacy": "aggregate_only_no_process_arguments",
        "formal_qualification": False,
    }
    if stage_timing is not None:
        record["stage_timing"] = stage_timing
    if isinstance(log_sha256, str) and log_sha256:
        record["log_sha256"] = log_sha256
    return record


def evidence_complete(record: dict[str, Any]) -> bool:
    """No arm counts as matched without sampled RSS and a verified 2-CPU quota."""
    return (record.get("rss_evidence_complete") is True
            and record.get("cpu_quota_complete") is True)


def comparability_check(
    records: list[dict[str, Any]],
    cases: tuple[str, ...] = CASES,
) -> dict[str, Any]:
    """Fail-closed comparability decision for a complete AB/BA evidence set."""
    reasons: list[str] = []
    ratios: list[float] = []
    expected = len(alternating_schedule(tuple(cases)))
    if not records or len(records) != expected:
        reasons.append("incomplete AB/BA evidence set")
    for record in records:
        label = str(record.get("case")) + "/" + str(record.get("arm"))
        if not evidence_complete(record):
            reasons.append(label + " missing sampled RSS or container CPU quota")
        quota = record.get("cpu_quota") or {}
        if quota.get("observed_cpu_max_origin") not in KERNEL_QUOTA_ORIGINS:
            reasons.append(label + " no observed kernel CPU quota")
        if quota.get("container_effective_cpus") != COMPARABILITY[
            "required_container_effective_cpus"
        ]:
            reasons.append(label + " container CPU quota mismatch")
        if quota.get("memory_limit_bytes") != int(CONSTRAINTS["memory"]):
            reasons.append(label + " memory limit mismatch")
        for phase in ("host_before", "host_after"):
            host = record.get(phase)
            if not isinstance(host, dict):
                reasons.append(label + " " + phase + " missing")
                continue
            decision = contention_check(host)
            if decision["abort"]:
                reasons.append(label + " " + phase + " contention: "
                               + ", ".join(decision["reasons"]))
            if decision["loadavg_per_cpu"] is not None:
                ratios.append(decision["loadavg_per_cpu"])
    if ratios and min(ratios) > 0 and (
            max(ratios) / min(ratios)
            > COMPARABILITY["max_host_load_ratio_between_arms"]):
        reasons.append("host load imbalance between arms")
    return {"comparable": not reasons, "abort": bool(reasons),
            "reasons": reasons}


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
    cases: tuple[str, ...] = CASES,
) -> dict[str, Any]:
    requested = tuple(cases)
    if not requested:
        raise Refusal("no cases requested")
    unknown = [c for c in requested if c not in READ_SHA256]
    if unknown:
        raise Refusal("unknown case: " + ", ".join(unknown))
    # Verify the immutable receipt once, before reading any value from it.
    # It pins all four tail cases regardless of which controls are requested.
    receipt = load_receipt(receipt_path, cases=CASES)
    gate = readiness(attestation)
    steps = alternating_schedule(requested)
    rows = {row["case"]: row for row in receipt.get("cases", [])}
    historical_cases = {}
    for case in requested:
        if case in rows:
            row = rows[case]
            historical_cases[case] = {
                "candidate_seconds": row["candidate_seconds"],
                "frozen_seconds": row["frozen_seconds"],
                "native_delta_seconds": row.get("native_delta_seconds"),
                "unattributed_delta_seconds": row.get("unattributed_delta_seconds"),
                "source": "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json",
                "source_sha256": RECEIPT_SHA256,
            }
        elif case in CONTROL_HISTORICAL:
            ctrl = CONTROL_HISTORICAL[case]
            historical_cases[case] = {
                "candidate_seconds": ctrl["candidate_seconds"],
                "frozen_seconds": ctrl["frozen_seconds"],
                "native_delta_seconds": None,
                "unattributed_delta_seconds": None,
                "source": ctrl["source"],
                "source_sha256": ctrl.get("source_sha256"),
                "control": True,
            }
        else:
            raise Refusal("no historical pin for case: " + case)
    return {
        "schema": SCHEMA,
        "candidate_commit": CANDIDATE_COMMIT,
        "images": {"frozen": FROZEN_IMAGE, "candidate": CANDIDATE_IMAGE},
        "constraints": CONSTRAINTS,
        "inputs": pinned_inputs(verify_files, cases=requested),
        "output_root": str(output_root),
        "cases": list(requested),
        "schedule": [
            {**step, "argv": argv_for(step, output_root)} for step in steps
        ],
        "historical_receipt": {
            "sha256": RECEIPT_SHA256,
            "cases": historical_cases,
        },
        "host_evidence": host_evidence(),
        "dependencies": gate,
        "source_pins": SOURCE_PINS,
        "deployed_pins": DEPLOYED_PINS,
        "comparability_plan": COMPARABILITY,
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
    parser.add_argument("--cases", default=",".join(CASES),
                        help="comma-separated case IDs; includes ordinary controls when requested")
    args = parser.parse_args()
    cases = tuple(c.strip() for c in args.cases.split(",") if c.strip())
    plan = build_plan(
        args.receipt, args.output_root,
        verify_files=args.verify_files, attestation=args.attestation,
        cases=cases,
    )
    text = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.emit_plan is not None:
        target = check_output_root(args.emit_plan.parent)
        if args.emit_plan.name != "plan.json":
            raise Refusal("plan file must be plan.json in a fresh root")
        target.mkdir(parents=True, exist_ok=True)
        (target / "plan.json").write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
