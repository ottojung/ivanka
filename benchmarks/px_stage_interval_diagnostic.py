"""Retrospective elapsed intervals between MiCall log markers, not CPU timing.

Only use independently matched successful arms. Do not change receipts or
assign elapsed time outside the log span to an observed stage.
"""
import argparse
import hashlib
import itertools
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PREFIX = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})\[INFO\]micall\.[^:]+\(\): (.*)$")
MARKERS = (
    ("startup", r"Starting on "),
    ("sample_setup", r"Processing Sample "),
    ("merge_entropy", r"Running merge_for_entropy on Sample "),
    ("fastq_g2p", r"Running fastq_g2p on Sample "),
    ("native_assembly", r"Running de novo assembly on Sample "),
    ("assembly_tail", r"Assembled \d+ contigs in "),
    ("remap", r"Running remap on Sample "),
    ("sam2aln", r"Running sam2aln on Sample "),
    ("aln2counts", r"Running aln2counts on Sample "),
    ("coverage_plots", r"Running coverage_plots on Sample "),
    ("cascade_report", r"Running cascade_report on Sample "),
    ("sample_tail", r"Finished sample "),
    ("resistance", r"Running resistance on Sample "),
    ("resistance_report", r"Running resistance report on Sample "),
    ("run_tail", r"Finished resistance of Sample "),
    ("done", r"Done\.$"),
)
ORDER = [name for name, _ in MARKERS[:11]] + [
    "sam2aln", "aln2counts", "coverage_plots", "cascade_report",
] + [name for name, _ in MARKERS[11:]]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def intervals(log, official_seconds):
    marks = []
    for line in log.splitlines():
        match = PREFIX.match(line)
        if match:
            for name, pattern in MARKERS:
                if re.match(pattern, match[2]):
                    marks.append((name, datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S,%f")))
                    break
    if [name for name, _ in marks] != ORDER:
        raise ValueError("missing_or_unexpected_stage_order")
    totals = defaultdict(float)
    for (name, a), (_, b) in itertools.pairwise(marks):
        delta = (b - a).total_seconds()
        if delta < 0:
            raise ValueError("nonmonotonic_log_timestamps")
        totals[name] += delta
    span = sum(totals.values())
    # Millisecond log rounding can differ slightly from monotonic timing.
    # Preserve the signed difference, never silently clamp or redistribute it.
    return {"stage_intervals_seconds": dict(totals), "logged_span_seconds": span,
            "official_minus_logged_span_seconds": official_seconds - span}


def evaluate(root, native_path):
    payload = native_path.read_bytes()
    native = json.loads(payload)
    if native.get("schema") != "ivanka.px.native-runtime-diagnostic.v1":
        raise ValueError("wrong native diagnostic schema")
    reports = defaultdict(list)
    for path in root.glob("run-*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        if isinstance(obj, dict):
            reports[sha(data)].append((path, obj))
    rows = []
    for arm in native["arms"]:
        matches = reports[arm["launcher_report_sha256"]]
        if len(matches) != 1:
            raise ValueError("launcher report no longer unique")
        path, obj = matches[0]
        log_path = path.with_suffix(".log")
        if log_path.is_symlink() or not log_path.is_file():
            raise ValueError("launcher log unavailable")
        log = log_path.read_bytes()
        if sha(log) != arm["launcher_log_sha256"] or obj["log_sha256"] != sha(log):
            raise ValueError("launcher log changed")
        result = intervals(log.decode(errors="replace"), arm["end_to_end_seconds"])
        rows.append({"tool": arm["tool"], "cohort": arm["cohort"], "alias": arm["alias"],
                     "canonical_receipt_sha256": arm["canonical_receipt_sha256"],
                     "launcher_log_sha256": arm["launcher_log_sha256"],
                     "official_seconds": arm["end_to_end_seconds"], **result})
    groups = []
    for tool in sorted({r["tool"] for r in rows} | {"all"}):
        group = [r for r in rows if tool == "all" or r["tool"] == tool]
        sums = {stage: sum(r["stage_intervals_seconds"][stage] for r in group)
                for stage in sorted(set(ORDER) - {"done"})}
        official = sum(r["official_seconds"] for r in group)
        groups.append({"tool": tool, "n": len(group), "official_seconds": official,
                       "stage_intervals_seconds": sums,
                       "official_minus_logged_span_seconds": official - sum(sums.values()),
                       "median_absolute_span_difference_seconds": statistics.median(
                           abs(r["official_minus_logged_span_seconds"]) for r in group),
                       "max_absolute_span_difference_seconds": max(
                           abs(r["official_minus_logged_span_seconds"]) for r in group)})
    return {"schema": "ivanka.px.stage-interval-diagnostic.v1", "not_qualification": True,
            "native_diagnostic_sha256": sha(payload),
            "native_receipt_index_sha256": native["receipt_index_sha256"],
            "groups": groups, "arms": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--native-diagnostic", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    with a.output.open("x") as out:
        json.dump(evaluate(a.root, a.native_diagnostic), out, indent=2, sort_keys=True)
        out.write("\n")


if __name__ == "__main__":
    main()
