"""Read-only retrospective PX native assembly timing decomposition.

Match canonical scheduler receipts to exactly one retained launcher report/log.
Only aggregates are public; this is neither a new score nor a measured MiCall
stage attribution. Unknown/ambiguous evidence stays explicitly unavailable.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ASSEMBLY = re.compile(
    r"Assembled (\d+) contigs in (\d+):(\d+):(\d+(?:\.\d+)?)\b")
SHA = re.compile(r"[a-f0-9]{64}\Z")
IDENT = re.compile(r"[a-z0-9-]+-(?:physical|synthetic)-PX-[RH]\d{3}\Z")


def duration(text):
    matches = ASSEMBLY.findall(text)
    if len(matches) != 1:
        raise ValueError("missing_or_ambiguous_native_duration")
    n, h, m, s = matches[0]
    h, m, s = int(h), int(m), float(s)
    if m >= 60 or s >= 60:
        raise ValueError("invalid_native_duration")
    return int(n), 3600 * h + 60 * m + s


def measurement(arm, launcher, log):
    if (launcher.get("status") != "finished"
            or launcher.get("exit_code") != 0
            or launcher.get("tool") != arm["tool_id"]
            or not SHA.fullmatch(str(launcher.get("bound_cid", "")))):
        raise ValueError("launcher_not_attested_success")
    if not log.is_file() or log.is_symlink():
        raise ValueError("missing_launcher_log")
    payload = log.read_bytes()
    if hashlib.sha256(payload).hexdigest() != arm["runner_receipt_sha256"]:
        raise ValueError("launcher_log_digest_mismatch")
    wall = arm["seconds"]
    if (isinstance(wall, bool) or not isinstance(wall, (int, float))
            or not math.isfinite(wall) or not 0 < wall <= 2400):
        raise ValueError("invalid_end_to_end_duration")
    contigs, native = duration(payload.decode(errors="replace"))
    if native > wall:
        raise ValueError("native_duration_exceeds_total")
    return {"contigs": contigs, "native_seconds": native,
            "end_to_end_seconds": wall, "unattributed_seconds": wall - native,
            "native_fraction": native / wall}


def evaluate(root):
    root = Path(root)
    index_path = root / "receipts/index.json"
    before = index_path.read_bytes()
    index = json.loads(before)["entries"]
    if not isinstance(index, dict):
        raise ValueError("invalid index")
    reports = defaultdict(list)
    for path in sorted(root.glob("run-*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            payload = path.read_bytes()
            value = json.loads(payload)
        except (OSError, ValueError):
            continue
        key = value.get("log_sha256") if isinstance(value, dict) else None
        if isinstance(key, str) and SHA.fullmatch(key):
            reports[key].append((path, value, hashlib.sha256(payload).hexdigest()))
    rows, excluded = [], defaultdict(Counter)
    counts = defaultdict(Counter)
    for key, expected in sorted(index.items()):
        if not IDENT.fullmatch(key) or not SHA.fullmatch(expected):
            raise ValueError("invalid index entry")
        path = root / "receipts" / (key + ".json")
        if not path.is_file() or path.is_symlink():
            raise ValueError("invalid canonical receipt path")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("canonical receipt digest mismatch")
        arm = json.loads(payload)
        tool = arm["tool_id"]
        cohort = arm["cohort"]
        if (key != f"{tool}-{cohort}-{arm['alias']}"
                or arm.get("schema") != "ivanka.px.case.receipt.v1"
                or arm.get("terminal") is not True
                or arm.get("qualifying") is not False
                or arm.get("outcome") not in ("success", "failure")):
            raise ValueError("receipt identity mismatch")
        group = (tool, cohort)
        counts[group][arm["outcome"]] += 1
        if arm["outcome"] != "success":
            excluded[group]["non_success_receipt"] += 1
            continue
        matches = reports.get(arm.get("runner_receipt_sha256"), [])
        if len(matches) != 1:
            excluded[group]["missing_or_ambiguous_launcher_report"] += 1
            continue
        report_path, launcher, report_digest = matches[0]
        try:
            measured = measurement(arm, launcher, report_path.with_suffix(".log"))
        except (ValueError, OSError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "unreadable_launcher"
            excluded[group][reason] += 1
            continue
        measured["launcher_report_sha256"] = report_digest
        rows.append({"tool": tool, "cohort": cohort, "alias": arm["alias"],
                     "canonical_receipt_sha256": expected,
                     "launcher_log_sha256": arm["runner_receipt_sha256"], **measured})
    if index_path.read_bytes() != before:
        raise ValueError("index changed during audit; retry on fresh snapshot")
    groups = []
    for tool, cohort in sorted(counts):
        key = (tool, cohort)
        group = [r for r in rows if (r["tool"], r["cohort"]) == key]
        total = sum(r["end_to_end_seconds"] for r in group)
        native = sum(r["native_seconds"] for r in group)
        groups.append({"tool": tool, "cohort": cohort,
                       "outcomes": dict(counts[key]), "matched_successes": len(group),
                       "unavailable": dict(excluded[key]),
                       "sum_end_to_end_seconds": total,
                       "sum_native_seconds": native,
                       "sum_unattributed_seconds": total - native,
                       "weighted_native_fraction": native / total if total else None,
                       "median_native_fraction": statistics.median(r["native_fraction"] for r in group) if group else None,
                       "median_end_to_end_seconds": statistics.median(r["end_to_end_seconds"] for r in group) if group else None,
                       "median_contigs": statistics.median(r["contigs"] for r in group) if group else None})
    return {"schema": "ivanka.px.native-runtime-diagnostic.v1", "not_qualification": True,
            "receipt_index_sha256": hashlib.sha256(before).hexdigest(),
            "indexed_count": len(index), "matched_successes": len(rows),
            "groups": groups, "arms": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = evaluate(a.root)
    with a.output.open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
