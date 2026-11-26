"""Retrospective decomposition of retained ultradeep timings, not a gate."""
import argparse
import csv
import json
import math
from pathlib import Path
import re

from pcr_jackpot_read_support import digest

CASES = {f"ultradeep-s{i:03d}" for i in range(16)}
TIMING_ORIGIN = "micall_in_container_monotonic_v1"
ASSEMBLY = re.compile(r"Assembled (\d+) contigs in (\d+):(\d+):(\d+(?:\.\d+)?)")


def native_duration(log):
    matches = ASSEMBLY.findall(log)
    if len(matches) != 1:
        raise ValueError("expected exactly one native assembly duration")
    count, hours, minutes, seconds = matches[0]
    h, m, s = int(hours), int(minutes), float(seconds)
    if m >= 60 or s >= 60:
        raise ValueError("invalid native assembly duration")
    return int(count), 3600 * h + 60 * m + s


def ledger(path):
    rows = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row["family"] != "ultradeep":
            continue
        case = row["id"]
        if case not in CASES or case in rows:
            raise ValueError("duplicate or unexpected ultradeep case")
        arm = row["results"]["ivanka"]
        seconds = arm.get("seconds")
        if (arm.get("status") != "success"
                or arm.get("timing_origin") != TIMING_ORIGIN
                or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or not 0 < seconds <= 2400):
            raise ValueError("unusable end-to-end timing")
        rows[case] = arm
    if set(rows) != CASES:
        raise ValueError("incomplete ultradeep cohort")
    return rows


def contig_sequences(path):
    with path.open() as stream:
        return [r["contig"] for r in csv.DictReader(stream)]


def compare_times(candidate, frozen, new_native, old_native):
    if not 0 <= new_native <= candidate or not 0 <= old_native <= frozen:
        raise ValueError("native duration exceeds end-to-end duration")
    delta = candidate - frozen
    native_delta = new_native - old_native
    return {"candidate_seconds": candidate, "frozen_seconds": frozen,
            "candidate_native_seconds": new_native, "frozen_native_seconds": old_native,
            "end_to_end_delta_seconds": delta, "native_delta_seconds": native_delta,
            "unattributed_delta_seconds": delta - native_delta}


def evaluate(candidate, frozen):
    new_ledger, old_ledger = candidate / "results.jsonl", frozen / "results.jsonl"
    new, old = ledger(new_ledger), ledger(old_ledger)
    rows = []
    for case in sorted(CASES):
        a, b = candidate / case, frozen / case / "ivanka"
        ac, bc = a / "unstitched_contigs.csv", b / "unstitched_contigs.csv"
        am, bm = a / "conseq.csv", b / "conseq.csv"
        al, bl, bo = a / "podman.log", b / "stderr.log", b / "stdout.log"
        cn, ct = native_duration(al.read_text())
        fn, ft = native_duration(bl.read_text() + "\n" + bo.read_text())
        same_contigs = contig_sequences(ac) == contig_sequences(bc)
        same_consensus = digest(am) == digest(bm)
        row = {"case": case, "candidate_contigs": cn, "frozen_contigs": fn,
               "ordered_unstitched_sequences_identical": same_contigs,
               "conseq_csv_bytes_identical": same_consensus,
               "candidate_score": new[case]["score"], "frozen_score": old[case]["score"],
               **compare_times(new[case]["seconds"], old[case]["seconds"], ct, ft),
               "input_sha256": {name: digest(path) for name, path in (
                   ("candidate_contigs", ac), ("frozen_contigs", bc),
                   ("candidate_conseq", am), ("frozen_conseq", bm),
                   ("candidate_log", al), ("frozen_stderr", bl), ("frozen_stdout", bo))}}
        rows.append(row)
    return {
        "schema": "ivanka.ultradeep-runtime-diagnostic.v1", "not_qualification": True,
        "candidate_results_sha256": digest(new_ledger),
        "frozen_results_sha256": digest(old_ledger),
        "timing_origin": TIMING_ORIGIN,
        "case_count": len(rows),
        "same_unstitched_count": sum(x["ordered_unstitched_sequences_identical"] for x in rows),
        "same_conseq_bytes_count": sum(x["conseq_csv_bytes_identical"] for x in rows),
        "sum_end_to_end_delta_seconds": sum(x["end_to_end_delta_seconds"] for x in rows),
        "sum_native_delta_seconds": sum(x["native_delta_seconds"] for x in rows),
        "sum_unattributed_delta_seconds": sum(x["unattributed_delta_seconds"] for x in rows),
        "cases": rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-root", "frozen-root", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    report = evaluate(a.candidate_root, a.frozen_root)
    with a.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
