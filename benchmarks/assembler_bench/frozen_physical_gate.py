"""Read-only physical score/runtime acceptance under original frozen MiCall."""
import argparse
import json

from psi_acceptance import summarize

from .frozen_contract import IMAGES
from .frozen_physical_data import load, success
from .frozen_receipts import attest


def analyze(root):
    proof = attest(root)
    data = load(root)
    ids = sorted(data["ivanka"])
    failures = []
    for h in ids:
        iv = data["ivanka"][h]
        if not success(iv):
            failures.append({"case": h, "reason": "ivanka_failed"})
            continue
        scores = [data[t][h]["measurement"]["score"] for t in IMAGES
                  if t != "ivanka" and success(data[t][h])]
        if not scores or 10 * iv["measurement"]["score"] < 9 * max(scores):
            failures.append({"case": h, "candidate": iv["measurement"]["score"],
                             "best_available": max(scores, default=None)})
    results = {}
    for rival in IMAGES:
        if rival == "ivanka":
            continue
        matched = [h for h in ids if success(data["ivanka"][h])
                   and success(data[rival][h])]
        score = [data["ivanka"][h]["measurement"]["score"] -
                 data[rival][h]["measurement"]["score"] for h in matched]
        runtime = [data[rival][h]["measurement"]["seconds"] -
                   data["ivanka"][h]["measurement"]["seconds"] for h in matched]
        results[rival] = {"paired": len(matched),
                          "historical_failed_arms": 198 -
                          sum(not data[rival][h]["failed"] for h in ids),
                          "score_psi": summarize(score),
                          "runtime_psi": summarize(runtime)}
    return {"source": "original-frozen-8458f9e5-only", "original_receipts": proof,
            "physical_cases": 198, "floor_failures": failures,
            "rivals": results, "qualification_pass": not failures and
            all(x["score_psi"]["positive_all_nonnegative"] and
                x["runtime_psi"]["positive_all_nonnegative"]
                for x in results.values()),
            "no_benchmarks_rerun": True, "resource_peak_RSS_unverified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.frozen_root), sort_keys=True))
