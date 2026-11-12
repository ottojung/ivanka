"""Combine real and synthetic matrices without silently dropping records."""
import argparse
import json
from pathlib import Path

from .gate import summarize_gate


def combine(real_path, synthetic_path, output_path):
    paths = [Path(real_path), Path(synthetic_path)]
    rows = []
    for path in paths:
        with path.open() as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    # The strict, all-tools gate enforces 198 real + 400 synthetic and
    # produces an audit report. Do not truncate partial input files.
    report = summarize_gate(rows)
    output = Path(output_path)
    with output.open("x") as file:
        json.dump(report, file, indent=2, sort_keys=True)
        file.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("real_jsonl", type=Path)
    parser.add_argument("synthetic_jsonl", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = combine(args.real_jsonl, args.synthetic_jsonl, args.output)
    print("EXPANDED_BENCHMARK_PASS" if report["pass"]
          else "EXPANDED_BENCHMARK_NOT_PASSED",
          "errors", len(report["errors"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
