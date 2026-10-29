#!/usr/bin/env python3
"""Fail-closed, per-invocation Riva alpha benchmark reporting."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys


def load_records(path):
    groups = defaultdict(list)
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark JSON at line {number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Expected JSON object at line {number}")
        if isinstance(row.get("invocation_id"), str) and row["invocation_id"]:
            groups[row["invocation_id"]].append(row)
    return groups


def evaluate_invocation(invocation, records, expected_samples):
    reasons = []
    starts, completed = {}, {}
    for row in records:
        sample, status = row.get("sample"), row.get("status")
        if not isinstance(sample, str) or not sample:
            reasons.append("missing sample identity")
            continue
        if status == "started":
            target = starts
        elif status in ("evaluated", "error"):
            target = completed
        else:
            reasons.append("invalid record status")
            continue
        if sample in target:
            reasons.append("duplicate sample record")
        target[sample] = row
    if set(starts) != expected_samples or set(completed) != expected_samples:
        reasons.append("not exactly the seven frozen controls")
    if {r.get("mode") for r in records} not in ({"riva"}, {"all"}):
        reasons.append("inconsistent benchmark mode")
    hashes = {r.get("riva_binary_sha256") for r in records}
    if len(hashes) != 1 or not isinstance(next(iter(hashes), None), str) or not re.fullmatch(r"[0-9a-f]{64}", next(iter(hashes))):
        reasons.append("missing or inconsistent binary SHA256")
    if any(r.get("cached_inputs") is not True for r in records):
        reasons.append("acceptance inputs not frozen")
    try:
        wall = round(max(r["timestamp"] + r["seconds"] for r in completed.values())
                     - min(r["timestamp"] for r in starts.values()), 2)
        if wall < 0 or wall > 1200:
            reasons.append("20-minute wall-clock limit exceeded or invalid")
    except (KeyError, ValueError, TypeError):
        wall = None
        reasons.append("incomplete timing information")
    failed = [sample for sample in sorted(expected_samples)
              if completed.get(sample, {}).get("status") != "evaluated"
              or completed[sample].get("alpha_pass") is not True]
    if failed:
        reasons.append("one or more sample alpha gates failed")
    return {"invocation_id": invocation, "pass": not reasons,
            "passed_samples": len(expected_samples) - len(failed),
            "completed": len(completed), "expected": len(expected_samples),
            "wall_seconds": wall, "riva_binary_sha256": next(iter(hashes), None) if len(hashes) == 1 else None,
            "failed_samples": failed, "reasons": sorted(set(reasons))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("benchmark-results/results.jsonl"))
    parser.add_argument("--roles", type=Path, default=Path("/workspace/riva-benchmark-cache/roles.json"))
    parser.add_argument("--invocation", help="Optional exact invocation for CI exit status")
    parser.add_argument("--latest", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    expected = json.loads(args.roles.read_text())
    if not isinstance(expected, dict) or len(expected) != 7:
        parser.error("--roles must be exactly the seven frozen controls")
    groups = load_records(args.results)
    if args.invocation and args.invocation not in groups:
        parser.error("unknown invocation")
    if args.latest < 1:
        parser.error("--latest must be positive")
    invocations = ([args.invocation] if args.invocation else
                   sorted(groups, key=lambda inv: max(r.get("timestamp", 0) for r in groups[inv]), reverse=True)[:args.latest])
    reports = [evaluate_invocation(inv, groups[inv], set(expected)) for inv in invocations]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            print(f'{"PASS" if r["pass"] else "NOT PASS"} {r["invocation_id"]}: '
                  f'{r["passed_samples"]}/{r["expected"]} passed; '
                  f'wall={r["wall_seconds"]}; sha256={r["riva_binary_sha256"]}')
            for problem in r["reasons"]:
                print("  -", problem)
    return 0 if not args.invocation or (reports and reports[0]["pass"]) else 1


if __name__ == "__main__":
    sys.exit(main())
