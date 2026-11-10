"""Paired diagnostic PSI comparison (never an acceptance gate).

Values come from each arm's MiCall CSVs and use exactly the same signed-power
solver as alignment/runtime. Partial coverage is reported, not zero-imputed.
"""
import argparse
import json
from pathlib import Path

from diagnostic_metrics import DIRECTIONS, UNITS, extract
from psi_acceptance import summarize


def compare_records(records, expected_count=None):
    terminal_records = list(records)
    names = [r.get("sample") for r in terminal_records]
    if None in names or len(set(names)) != len(names):
        raise ValueError("every terminal record needs a unique sample")
    # A failed or timed-out sample may have partial CSVs. Do not treat its
    # partial measurements as a valid A/B pair, even for non-gating PSI.
    excluded = [r for r in terminal_records if
                r.get("status") != "finished" or r.get("failed") is not False]
    records = [r for r in terminal_records if
               r.get("status") == "finished" and r.get("failed") is False]
    excluded_names = [r["sample"] for r in excluded]
    metrics = {}
    for name, direction in DIRECTIONS.items():
        diffs = []
        missing = list(excluded_names)
        for record in records:
            iva = record.get("iva", {}).get("metrics", {}).get("diagnostics", {})
            ivanka = record.get("ivanka", {}).get("metrics", {}).get("diagnostics", {})
            left = iva.get("values", {}).get(name)
            right = ivanka.get("values", {}).get(name)
            if (not isinstance(left, (int, float)) or isinstance(left, bool)
                    or not isinstance(right, (int, float)) or isinstance(right, bool)):
                missing.append(record["sample"])
                continue
            import math
            if not (math.isfinite(left) and math.isfinite(right)):
                missing.append(record["sample"])
                continue
            diffs.append(direction * (right-left))
        result = {"direction": "higher" if direction == 1 else "lower",
                  "units": UNITS[name], "paired_samples": len(diffs),
                  "missing_samples": missing,
                  "psi": None, "psi_error": None}
        if diffs:
            try:
                result["psi"] = summarize(diffs)
            except (ValueError, ArithmeticError, OverflowError) as exc:
                result["psi_error"] = f"{type(exc).__name__}: {exc}"
        metrics[name] = result
    return {"schema": "ivanka.diagnostic_psi.v1",
            "qualification_effect": "none",
            "qualifying_metrics_unchanged": ["final_max_alignment", "micall_runtime"],
            "samples_seen": len(terminal_records),
            "successful_paired_samples": len(records),
            "excluded_terminal_samples": [
                {"sample": r["sample"], "status": r.get("status"),
                 "failed": r.get("failed")}
                for r in excluded],
            "expected_samples": expected_count,
            "cohort_complete": (len(records) == expected_count
                                and not excluded
                                if expected_count is not None else None),
            "metrics": metrics}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_jsonl", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--expected-samples", type=int)
    p.add_argument("--refresh-from-artifacts", action="store_true",
                   help="Read diagnostic CSVs from recorded artifact dirs; no original record edits")
    p.add_argument("--exact-coverage-sidecars", type=Path,
                   help="Optional independent sidecars at ROOT/sample/arm/exact_coverage.csv")
    a = p.parse_args(argv)
    with a.results_jsonl.open() as f:
        records = [json.loads(line) for line in f if line.strip()]
    # A runner includes a 'started' row followed by a terminal row. The
    # comparison is of terminal records only; a partial cohort stays partial.
    records = [r for r in records if r.get("status") != "started"]
    if a.refresh_from_artifacts:
        for record in records:
            for arm in ("iva", "ivanka"):
                instance = record.get(arm, {})
                root = instance.get("artifact_dir")
                if root and Path(root).is_dir():
                    overlay = None
                    if a.exact_coverage_sidecars is not None:
                        overlay = a.exact_coverage_sidecars / record["sample"] / arm
                    instance.setdefault("metrics", {})["diagnostics"] = extract(
                        root, exact_coverage_root=overlay)
    report = compare_records(records, a.expected_samples)
    report["refreshed_from_artifacts"] = a.refresh_from_artifacts
    report["exact_coverage_sidecars"] = (str(a.exact_coverage_sidecars)
                                         if a.exact_coverage_sidecars else None)
    report["physical_artifact_integrity_attested"] = False
    formatted = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        if a.output.exists():
            raise FileExistsError("refusing to overwrite diagnostic PSI report")
        a.output.write_text(formatted + "\n")
    else:
        print(formatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
