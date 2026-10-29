#!/usr/bin/env python3
"""Fail-closed reports of the current complete 20-sample full-MiCall runs.

Consumes runner-written summary-<invocation>.json objects, not the superseded
seven-control Riva-only benchmark JSONL format.
"""
import argparse
import json
from pathlib import Path
import re
import sys

MAX_WALL_SECONDS = 2400
REQUIRED_SAMPLES = 20
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def evaluate(summary):
    reasons = []
    if not isinstance(summary, dict):
        return {"invocation": None, "pass": False, "reasons": ["invalid summary object"]}
    invocation = summary.get("invocation")
    if not isinstance(invocation, str) or not invocation:
        reasons.append("missing invocation ID")
    if summary.get("qualification_requested") is not True or summary.get("mode") != "both":
        reasons.append("not a qualifying both-arm run")
    if summary.get("allow_missing_baseline") is not False:
        reasons.append("non-strict or missing baseline mode")
    for name in ("manifest_sample_count", "selected_samples", "finished_samples", "accepted_samples"):
        if type(summary.get(name)) is not int or summary[name] != REQUIRED_SAMPLES:
            reasons.append(f"not exactly {REQUIRED_SAMPLES} {name}")
    if summary.get("failed_samples") != []:
        reasons.append("failed or unspecified samples")
    elapsed = summary.get("global_seconds")
    configured = summary.get("global_limit_seconds")
    if (type(elapsed) not in (int, float) or type(configured) not in (int, float)
            or not (0 <= elapsed <= MAX_WALL_SECONDS)
            or not (0 < configured <= MAX_WALL_SECONDS)
            or elapsed > configured):
        reasons.append("40-minute qualification limit missing or exceeded")
    for name in ("manifest_sha256", "hxb2_sha256", "project_reference_catalog_sha256"):
        value = summary.get(name)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            reasons.append(f"missing or invalid {name}")
    images = summary.get("images")
    for role in ("iva", "riva"):
        value = images.get(role) if isinstance(images, dict) else None
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            reasons.append(f"missing or invalid {role} image digest")
    if summary.get("full_alpha_pass") is not True:
        reasons.append("runner did not certify full_alpha_pass")
    return {
        "invocation": invocation, "pass": not reasons,
        "accepted_samples": summary.get("accepted_samples"),
        "finished_samples": summary.get("finished_samples"),
        "global_seconds": elapsed,
        "full_alpha_pass": summary.get("full_alpha_pass") is True,
        "reasons": reasons,
    }


def load_reports(path):
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("summary-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        raise ValueError("results must be a summary JSON file or a results directory")
    if not files:
        raise ValueError("no summary-*.json reports found")
    reports = []
    seen = set()
    for filename in files:
        try:
            report = evaluate(json.loads(filename.read_text()))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"invalid summary JSON: {filename.name}") from exc
        key = report["invocation"]
        if key in seen:
            raise ValueError(f"duplicate invocation ID: {key}")
        seen.add(key)
        reports.append(report)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("benchmark-results"))
    parser.add_argument("--invocation", help="Select an exact invocation and return its pass/fail exit status")
    parser.add_argument("--latest", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.latest < 1:
        parser.error("--latest must be positive")
    try:
        reports = load_reports(args.results)
    except ValueError as exc:
        parser.error(str(exc))
    if args.invocation:
        reports = [r for r in reports if r["invocation"] == args.invocation]
        if not reports:
            parser.error("unknown invocation")
    else:
        reports = reports[:args.latest]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(f'{"PASS" if report["pass"] else "NOT PASS"} {report["invocation"]}: '
                  f'{report["accepted_samples"]}/{REQUIRED_SAMPLES} accepted, '
                  f'elapsed={report["global_seconds"]}')
            for reason in report["reasons"]:
                print("  -", reason)
    return 0 if not args.invocation or reports[0]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
