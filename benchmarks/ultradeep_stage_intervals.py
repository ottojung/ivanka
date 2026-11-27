"""Locate historical elapsed differences between retained MiCall log markers.

This is an observational diagnostic, not causal CPU profiling, a rerun,
or a qualification result. Reuse the exact prior ledger and log bindings.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from px_stage_interval_diagnostic import intervals, ORDER
from ultradeep_runtime_diagnostic import evaluate

PRIOR_SHA256 = "7d0726a5cf6d6f9bb7a42689402633fe44ad5c30621fa7881b0862fe6b262e5c"
STAGES = tuple(dict.fromkeys(name for name in ORDER if name != "done"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def arm(path, expected, seconds):
    log = path.read_bytes()
    require(sha(log) == expected, "retained log digest changed")
    require(type(seconds) in (float, int) and math.isfinite(seconds)
            and 0 < seconds <= 2400, "invalid official duration")
    result = intervals(log.decode("utf-8"), seconds)
    require(set(result["stage_intervals_seconds"]) == set(STAGES),
            "incomplete stage intervals")
    return {"official_seconds": seconds, "log_sha256": expected, **result}


def paired(row, candidate, frozen):
    pins = row["input_sha256"]
    require(row["ordered_unstitched_sequences_identical"] is True
            and row["conseq_csv_bytes_identical"] is True,
            "historical paired output identity changed")
    require(row["candidate_score"] == row["frozen_score"],
            "historical paired score mismatch")
    case = row["case"]
    a, b = candidate / case, frozen / case / "ivanka"
    require(sha((b / "stdout.log").read_bytes()) == pins["frozen_stdout"]
            == sha(b""), "unexpected frozen stdout; ambiguous marker stream")
    c = arm(a / "podman.log", pins["candidate_log"], row["candidate_seconds"])
    f = arm(b / "stderr.log", pins["frozen_stderr"], row["frozen_seconds"])
    delta = {s: c["stage_intervals_seconds"][s] - f["stage_intervals_seconds"][s]
             for s in STAGES}
    residual = c["official_minus_logged_span_seconds"] - f["official_minus_logged_span_seconds"]
    official = row["end_to_end_delta_seconds"]
    require(math.isclose(sum(delta.values()) + residual, official, abs_tol=1e-6),
            "elapsed interval accounting mismatch")
    return {"case": case, "candidate": c, "frozen": f,
            "delta_seconds": delta, "official_delta_seconds": official,
            "outside_logged_span_delta_seconds": residual}


def report(candidate, frozen, prior_path):
    prior_bytes = prior_path.read_bytes()
    require(sha(prior_bytes) == PRIOR_SHA256, "prior diagnostic identity changed")
    prior = json.loads(prior_bytes)
    observed = evaluate(candidate, frozen)
    require(observed == prior, "prior ledger/log/output evidence no longer reproduces")
    rows = [paired(row, candidate, frozen) for row in prior["cases"]]
    require(len(rows) == 16, "incomplete paired cohort")
    totals = {s: sum(row["delta_seconds"][s] for row in rows) for s in STAGES}
    official = sum(row["official_delta_seconds"] for row in rows)
    outside = sum(row["outside_logged_span_delta_seconds"] for row in rows)
    require(math.isclose(sum(totals.values()) + outside, official, abs_tol=1e-6),
            "aggregate interval accounting mismatch")
    return {"schema": "ivanka.p1.ultradeep-stage-intervals.v1",
            "not_qualification": True, "prior_diagnostic_sha256": PRIOR_SHA256,
            "candidate_results_sha256": prior["candidate_results_sha256"],
            "frozen_results_sha256": prior["frozen_results_sha256"],
            "timing_origin": prior["timing_origin"], "case_count": len(rows),
            "official_delta_seconds": official,
            "stage_delta_seconds": totals,
            "outside_logged_span_delta_seconds": outside, "cases": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-root", "frozen-root", "prior-report", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    result = report(a.candidate_root, a.frozen_root, a.prior_report)
    with a.output.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
