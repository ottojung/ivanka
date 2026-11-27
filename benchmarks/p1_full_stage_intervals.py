"""Retrospective paired synthetic log-marker accounting, never qualification."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from px_stage_interval_diagnostic import intervals, ORDER
from ultradeep_runtime_diagnostic import contig_sequences, TIMING_ORIGIN

PINS = {
    "candidate": ("903ff012e4e35b0bc7b83c147c56f8ff3c5adc017d188a4679438c7e16eea10d",
                  "6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971"),
    "frozen": ("7e1e81ce253fec2e4052db4843bfc580491c89bbc320a21374058f4297482203",
               "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"),
}
STAGES = tuple(dict.fromkeys(name for name in ORDER if name != "done"))
CASE = re.compile(r"([a-z0-9_]+)-s(00[0-9]|01[0-5])$")
SHA = re.compile(r"[0-9a-f]{64}$")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def ledger(path, tag):
    data = path.read_bytes()
    expected, image = PINS[tag]
    require(sha(data) == expected, "ledger digest mismatch: " + tag)
    rows = {}
    for line in data.splitlines():
        row = json.loads(line)
        case = row["id"]
        match = CASE.fullmatch(case)
        require(match and match[1] == row["family"] and case not in rows,
                "invalid or duplicate case")
        require(SHA.fullmatch(row["input_sha256"]), "invalid input pin")
        arm = row["results"]["ivanka"]
        require(arm["sha256"] == image and arm["timing_origin"] == TIMING_ORIGIN,
                "image or timer origin drift")
        require(arm["status"] in ("success", "failed"), "nonterminal arm")
        rows[case] = row
    counts = Counter(row["family"] for row in rows.values())
    require(len(rows) == 464 and len(counts) == 29 and set(counts.values()) == {16},
            "incomplete historical roster")
    return rows


def timed_arm(path, result, tag):
    log_path = path / ("podman.log" if tag == "candidate" else "stderr.log")
    log = log_path.read_bytes()
    if tag == "frozen":
        require((path / "stdout.log").read_bytes() == b"", "ambiguous frozen stdout")
    timing_bytes = (path / "timing.json").read_bytes()
    timing = json.loads(timing_bytes)
    seconds = result["seconds"]
    require(type(seconds) in (float, int) and math.isfinite(seconds) and seconds > 0,
            "invalid official duration")
    require(timing["exit_code"] == 0 and timing["seconds"] == seconds
            and timing["timing_origin"] == TIMING_ORIGIN,
            "timing record and ledger disagree")
    require(result["exit_code"] == 0, "nonzero ledger exit")
    parsed = intervals(log.decode("utf-8"), seconds)
    require(set(parsed["stage_intervals_seconds"]) == set(STAGES),
            "incomplete marker set")
    return {"seconds": seconds, "log_sha256": sha(log),
            "timing_sha256": sha(timing_bytes),
            "conseq_sha256": sha((path / "conseq.csv").read_bytes()),
            "unstitched_csv_sha256": sha((path / "unstitched_contigs.csv").read_bytes()),
            **parsed}


def pair(case, candidate, frozen, new, old):
    require(new["input_sha256"] == old["input_sha256"] and new["family"] == old["family"],
            "unmatched case identity")
    c, f = new["results"]["ivanka"], old["results"]["ivanka"]
    require(c["status"] == f["status"], "historical paired status drift")
    common = {"case": case, "family": new["family"], "input_sha256": new["input_sha256"]}
    if c["status"] != "success":
        return {**common, "status": "not_evaluated", "reason": "both_arms_failed"}
    a, b = candidate / case, frozen / case / "ivanka"
    nc = timed_arm(a, c, "candidate")
    oc = timed_arm(b, f, "frozen")
    same_consensus = nc["conseq_sha256"] == oc["conseq_sha256"]
    same_contigs = contig_sequences(a / "unstitched_contigs.csv") == contig_sequences(
        b / "unstitched_contigs.csv")
    official_delta = nc["seconds"] - oc["seconds"]
    delta = {s: nc["stage_intervals_seconds"][s] - oc["stage_intervals_seconds"][s]
             for s in STAGES}
    outside = nc["official_minus_logged_span_seconds"] - oc["official_minus_logged_span_seconds"]
    require(math.isclose(sum(delta.values()) + outside, official_delta, abs_tol=1e-6),
            "paired interval accounting mismatch")
    return {**common, "status": "measured", "candidate": nc, "frozen": oc,
            "same_conseq_bytes": same_consensus, "same_ordered_unstitched": same_contigs,
            "same_score": c["score"] == f["score"], "official_delta_seconds": official_delta,
            "stage_delta_seconds": delta, "outside_logged_span_delta_seconds": outside}


def summarize(rows):
    require(rows and all(r["status"] == "measured" for r in rows),
            "summary requires measured rows")
    values = [r["official_delta_seconds"] for r in rows]
    total = sum(values)
    sums = {s: sum(r["stage_delta_seconds"][s] for r in rows) for s in STAGES}
    residual = sum(r["outside_logged_span_delta_seconds"] for r in rows)
    require(math.isclose(sum(sums.values()) + residual, total, abs_tol=1e-6),
            "aggregate interval accounting mismatch")
    return {"n": len(rows), "official_delta_seconds": total,
            "candidate_faster": sum(v < 0 for v in values),
            "candidate_equal": sum(v == 0 for v in values),
            "candidate_slower": sum(v > 0 for v in values),
            "median_delta_seconds": statistics.median(values),
            "stage_delta_seconds": sums, "outside_logged_span_delta_seconds": residual}


def report(candidate, frozen):
    new = ledger(candidate / "results.jsonl", "candidate")
    old = ledger(frozen / "results.jsonl", "frozen")
    require(set(new) == set(old), "unmatched cohort")
    rows = [pair(k, candidate, frozen, new[k], old[k]) for k in sorted(new)]
    measured = [r for r in rows if r["status"] == "measured"]
    require(len(measured) == 448, "unexpected paired measurement count")
    groups = defaultdict(list)
    for r in measured:
        groups["all"].append(r)
        groups["family:" + r["family"]].append(r)
        key = (r["same_conseq_bytes"], r["same_ordered_unstitched"])
        groups["output_identity:" + str(key)].append(r)
        if key == (True, True) and r["family"] != "ultradeep":
            groups["identical_excluding_ultradeep"].append(r)
    return {"schema": "ivanka.p1.full-stage-intervals.v1", "not_qualification": True,
            "scope": "retrospective matched input identities, unmatched execution resources",
            "ledger_sha256": {k: v[0] for k, v in PINS.items()},
            "image_sha256": {k: v[1] for k, v in PINS.items()},
            "timing_origin": TIMING_ORIGIN, "requested_cases": len(rows),
            "measured_pairs": len(measured),
            "summaries": {k: summarize(v) for k, v in sorted(groups.items())}, "cases": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-root", "frozen-root", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    result = report(a.candidate_root, a.frozen_root)
    with a.output.open("x") as f:
        json.dump(result, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")


if __name__ == "__main__":
    main()
