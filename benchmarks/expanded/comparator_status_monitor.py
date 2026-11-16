"""Observe actual six-comparator progress without restarting or editing MiCall.

The s6 'up' status alone is NOT evidence that a benchmark is executing.
This monitor only writes a separate, replace-atomically generated report.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from .comparator_first import TOOLS

ROOT = Path("/workspace")
SERVICE = ROOT / "ivanka-bench-live-service-20261113"
REAL = ROOT / "ivanka-comparators-real198-20261116/results"
SYNTH = ROOT / "ivanka-comparators-400-20261116/results"
ORIGINAL = ROOT / "ivanka-original-pair-real198-fresh2-20261115/invocation-finished.json"
ARCHIVE = ROOT / "ivanka-maintenance-20261115/archived-old-synthetic-coverage-20261116/completed.json"
SOURCES = {
    "physical": "b634bce15f6f1dfae0cf482de35436ffd5af72e0",
    "synthetic": "d4a60b39328dfee6f2cb0b05f0d01bdd8a42ba8b",
}
MODULES = {
    "physical": "benchmarks.expanded.comparator_real_first",
    "synthetic": "benchmarks.expanded.comparator_first",
}
MIN_FREE = 7 * 1024**3
PER_ACTIVE = 512 * 1024**2
START_FREE = 12 * 1024**3


def active_processes():
    """Read only real worker command lines, not synthetic supervisor PIDs."""
    found = {"physical": [], "synthetic": []}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
        for tag, module in MODULES.items():
            if (module.encode() in args
                    and b"-m" in args and b"--out" in args):
                index = args.index(b"--out")
                expected = REAL if tag == "physical" else SYNTH
                if index + 1 < len(args) and args[index + 1] == os.fsencode(expected):
                    found[tag].append(int(proc.name))
    return {name: sorted(pids) for name, pids in found.items()}


def records(path, tag):
    """Count unique terminal attempts; never conflate started events with done."""
    expected_samples = 198 if tag == "physical" else 400
    max_arms = expected_samples * len(TOOLS)
    manifest = path / "run_manifest.json"
    journal = path / "results.jsonl"
    counts = {name: {"finished": 0, "successful": 0, "failed": 0}
              for name in TOOLS}
    result = {"expected_arms": max_arms, "terminal_arms": 0,
              "successful": 0, "failed": 0, "by_assembler": counts}
    if not manifest.exists():
        if journal.exists():
            raise ValueError(f"journal without source manifest: {tag}")
        return result
    source = json.loads(manifest.read_text())
    if (source.get("source_commit") != SOURCES[tag]
            or source.get("expected_samples") != expected_samples
            or source.get("expected_arms") != max_arms
            or source.get("qualified") is not False
            or set(source.get("images", {})) != set(TOOLS)
            or (tag == "physical"
                and len(source.get("original_inputs", {})) != expected_samples)
            or (tag == "synthetic"
                and not source.get("truth_validation", {}).get("valid"))):
        raise ValueError("unverified frozen comparator source " + tag)
    result["source_commit"] = SOURCES[tag]
    if not journal.exists():
        return result
    raw = journal.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("journal line is incomplete: " + tag)
    result["journal_sha256"] = hashlib.sha256(raw).hexdigest()
    seen = set()
    for line in raw.splitlines():
        record = json.loads(line)
        assembler = record.get("assembler")
        identifier = record.get("sample" if tag == "physical" else "id")
        state = (record.get("status") if tag == "physical"
                 else record.get("result", {}).get("status"))
        if (assembler not in counts or not isinstance(identifier, str)
                or not identifier or (assembler, identifier) in seen
                or state not in ("success", "failed")):
            raise ValueError("unexpected or duplicate comparator arm: " + tag)
        seen.add((assembler, identifier))
        counts[assembler]["finished"] += 1
        counts[assembler]["successful" if state == "success" else "failed"] += 1
    if len(seen) > max_arms or any(v["finished"] > expected_samples
                                  for v in counts.values()):
        raise ValueError("more arms than frozen cohort: " + tag)
    result["terminal_arms"] = len(seen)
    result["successful"] = sum(v["successful"] for v in counts.values())
    result["failed"] = sum(v["failed"] for v in counts.values())
    return result


def classify(tag, data, pids, prereqs, free, cohort):
    if data["terminal_arms"] == data["expected_arms"]:
        marker = cohort / "attempt-finished.json"
        if marker.is_file():
            summary = json.loads(marker.read_text())
            if (summary.get("arms") != data["expected_arms"]
                    or summary.get("failed_arms") != data["failed"]):
                raise ValueError("completion marker contradicts journal")
            return "completed", None
    if pids:
        return "executing", None
    missing = [name for name, passed in prereqs.items() if not passed]
    if missing:
        return "queued", ", ".join(missing)
    if free < (MIN_FREE + PER_ACTIVE):
        return "paused_low_disk", "below continuation reserve"
    if data["terminal_arms"] == 0 and free < START_FREE:
        return "queued_disk_guard", "below first-launch 12 GiB reserve"
    return "ready_or_retrying", "supervisor idle; worker not executing"


def snapshot(root=ROOT, running=None):
    root = Path(root)
    real = root / REAL.relative_to(ROOT)
    synthetic = root / SYNTH.relative_to(ROOT)
    original = root / ORIGINAL.relative_to(ROOT)
    archive = root / ARCHIVE.relative_to(ROOT)
    pids = active_processes() if running is None else running
    free = shutil.disk_usage(root).free
    real_data = records(real, "physical")
    synthetic_data = records(synthetic, "synthetic")
    original_done = original.is_file()
    archive_done = archive.is_file()
    for tag, data, cohort, conditions in (
            ("physical", real_data, real, {"original physical": original_done,
                                          "historical archive": archive_done}),
            ("synthetic", synthetic_data, synthetic,
             {"original physical": original_done,
              "historical archive": archive_done,
              "fixed physical comparators":
              (real / "attempt-finished.json").is_file()})):
        actual, reason = classify(tag, data, pids.get(tag, []),
                                  conditions, free, cohort)
        data.update({"execution_state": actual, "reason": reason,
                     "worker_pids": pids.get(tag, [])})
    return {
        "schema": "ivanka.comparator-first.actual-execution-status.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "qualified": False,
        "disk_free_bytes": free,
        "disk_headroom_at_ten_workers": free - MIN_FREE - 10 * PER_ACTIVE,
        "physical": real_data, "synthetic": synthetic_data,
        "original_physical_completed": original_done,
        "historical_coverage_archive_completed": archive_done,
        "source_pinned_comparators_have_priority": True,
    }


def write_atomic(path, payload):
    path = Path(path)
    if not path.parent.is_dir() or path.is_symlink():
        raise ValueError("monitor output directory missing or redirected")
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("stale monitor partial output")
    with temporary.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.interval_seconds < 10:
        parser.error("status interval must be at least 10 seconds")
    while True:
        try:
            result = snapshot()
            write_atomic(args.out, result)
            print("REAL_COMPARATOR_STATE", result["physical"]["execution_state"],
                  result["physical"]["terminal_arms"],
                  "SYNTH_COMPARATOR_STATE", result["synthetic"]["execution_state"],
                  result["synthetic"]["terminal_arms"],
                  "FREE_GIB", round(result["disk_free_bytes"] / 1024**3, 2),
                  flush=True)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("COMPARATOR_STATUS_OBSERVATION_ERROR", repr(exc), flush=True)
            if not args.loop:
                raise
        if not args.loop:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
