"""Compare matching prior floor-failure truths with prospective raw-read native evidence.

These are different preprocessing contexts. No attribution or integrated pass
may be inferred from this descriptive comparison.
"""
import argparse
import hashlib
import json
import statistics
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def evaluate(prior_bytes, new_bytes):
    prior, new = json.loads(prior_bytes), json.loads(new_bytes)
    require(prior["not_qualification"] is True and new["not_qualification"] is True,
            "qualification_boundary")
    require(new["raw_untrimmed_reads"] is True, "preprocessing_boundary")
    cases = [x for x in new["cases"] if x["family"] == "equal_strains"]
    mapping = {x["case"]: x for x in cases}
    require(len(cases) == len(mapping) == 16, "case_roster")
    rows, seen = [], set()
    for x in prior["cases"]:
        key = (x["case"], x["truth"])
        require(key not in seen, "duplicate_prior_truth")
        seen.add(key)
        y = mapping[x["case"]]
        matches = [z for z in y["panel"] if z["truth"] == x["truth"]]
        require(len(matches) == 1, "truth_identity")
        t = matches[0]
        for old_key, new_key in (("r1", "R1"), ("r2", "R2"), ("truth", "truth")):
            require(x["input_sha256"][old_key] == y["input_sha256"][new_key],
                    "input_drift")
        k = t["exclusive_kmers"]
        require(type(k) is int and k > 0 and k == x["read_observed_exclusive_truth_kmers"],
                "denominator_drift")
        row = {"case": x["case"], "truth": x["truth"],
               "read_observed_exclusive_kmers": k,
               "prior_recovered": x["candidate_raw_exclusive_recovered"],
               "new_native_recovered": t["exclusive_recovered"]["new"],
               "prior_best_rival_recovered": x["best_raw_exclusive_recovered"],
               "new_native_alignment_fraction": t["native_alignment_fraction"]["new"]}
        for c in ("prior_recovered", "new_native_recovered", "prior_best_rival_recovered"):
            require(type(row[c]) is int and 0 <= row[c] <= k, "recovery_count")
        rows.append(row)
    require(len(rows) == prior["failing_truth_count"] == 16, "prior_truth_count")
    cols = ("prior_recovered", "new_native_recovered", "prior_best_rival_recovered")
    return {
        "schema": "ivanka.equal-strain-native-cross-context-diagnostic.v1",
        "not_qualification": True, "different_preprocessing": True,
        "source_report_sha256": {
            "prior": hashlib.sha256(prior_bytes).hexdigest(),
            "new": hashlib.sha256(new_bytes).hexdigest()},
        "rows": rows,
        "medians": {c: statistics.median(x[c]/x["read_observed_exclusive_kmers"]
                                       for x in rows) for c in cols},
        "improved": sum(x[cols[1]] > x[cols[0]] for x in rows),
        "equal": sum(x[cols[1]] == x[cols[0]] for x in rows),
        "regressed": sum(x[cols[1]] < x[cols[0]] for x in rows),
        "below_90pct_rival_native_evidence": [
            [x["case"], x["truth"]] for x in rows if x[cols[1]] < .9*x[cols[2]]],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prior", type=Path)
    p.add_argument("new", type=Path)
    args = p.parse_args()
    print(json.dumps(evaluate(args.prior.read_bytes(), args.new.read_bytes()),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
