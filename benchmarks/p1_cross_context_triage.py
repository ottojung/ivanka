"""Read-only triage across historical integrated and prospective raw-native evidence.

Do not use this for qualification or feed any truth/score into assembly.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from native_adapter_mode_readback import validate, CASES
from expanded.score import reference_truths

LEDGER = "903ff012e4e35b0bc7b83c147c56f8ff3c5adc017d188a4679438c7e16eea10d"
NATIVE = "5e706eb8a8d8404bf49c2d35bdca86aab4697a75906b3c3f9c252911622ac19c"
POSTHOC = "6ad7784c0f0a1ed84d0fad5feae38fdf408115d7a4496d2f69e10280643a86fb"
IMAGE = "6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971"
RIVALS = ("abyss", "haploflow", "iva", "megahit", "spades", "velvet")
FLOOR = 0.9
EPS = 1e-7


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    data = path.read_bytes()
    require(sha(data) == expected, "retained source digest changed: " + path.name)
    return data


def fraction(value):
    require(type(value) in (int, float) and math.isfinite(value)
            and -EPS <= value <= 1 + EPS, "invalid alignment fraction")
    return value


def identity_row(arm, key, truth, abundance):
    row = arm["per_truth"][key]
    require(row["length"] == len(truth) and row["truth_sha256"] == sha(truth.encode())
            and row["nominal_abundance"] == abundance, "truth identity mismatch")
    value = fraction(row["fraction"])
    require(math.isclose(value, row["score"] / len(truth), abs_tol=EPS),
            "per-truth score mismatch")
    return value


def classify(historical, current, threshold, observed, exclusive):
    """Descriptive labels, not predictions or a substitute for integrated evaluation."""
    was_below = historical + EPS < threshold
    now_below = current + EPS < threshold
    if not was_below:
        return "historical_above_native_below" if now_below else "both_above"
    if not now_below:
        return "historical_below_native_above"
    if observed is None or exclusive is None:
        return "both_below_missing_evidence_denominator"
    if observed >= FLOOR and exclusive >= FLOOR:
        return "both_below_high_kmer_recovery"
    return "both_below_incomplete_kmer_recovery"


def matched_case(native, historical, data):
    case = native["case"]
    require(case == historical["id"] and native["family"] == historical["family"],
            "case mismatch")
    pins = native["input_sha256"]
    fingerprint = sha((pins["R1"] + pins["R2"]).encode())
    require(historical["input_sha256"] == fingerprint, "original input mismatch")
    directory = data / case
    spec = json.loads((directory / "manifest.json").read_bytes())
    require(spec["family"] == native["family"] and spec["score_model_revision"] == 2
            and spec["truth_is_evaluation_only"] is True, "cohort scoring model changed")
    names = {"reads/R1.fastq.gz": "R1", "reads/R2.fastq.gz": "R2",
             "hidden-truth/haplotypes.fasta": "truth"}
    require(all(spec["sha256"][name] == pins[tag] for name, tag in names.items()),
            "source manifest mismatch")
    truth_path = directory / "hidden-truth/haplotypes.fasta"
    pinned(truth_path, pins["truth"])
    truths = dict(reference_truths(spec, truth_path))
    require(set(truths) == {p["truth"] for p in native["panel"]}
            and len(truths) == len(native["panel"]), "abundant truth roster mismatch")
    arms = historical["results"]
    require(set(arms) == set(RIVALS) | {"ivanka"}, "historical rival roster drift")
    candidate = arms["ivanka"]
    require(candidate["status"] == "success" and candidate["sha256"] == IMAGE,
            "historical candidate missing or image drift")
    rivals = [name for name in RIVALS if arms[name]["status"] == "success"]
    require(rivals, "no successful historical rivals")
    for name in ["ivanka", *rivals]:
        require(set(arms[name]["per_truth"]) == set(truths), "truth roster drift")
    rows = []
    for p in native["panel"]:
        key = p["truth"]
        truth = truths[key]
        abundance = spec["nominal_fractions"][int(key.split("_")[1])]
        require(p["truth_length"] == len(truth), "native truth length mismatch")
        values = {name: identity_row(arms[name], key, truth, abundance)
                  for name in ["ivanka", *rivals]}
        best = max(values[name] for name in rivals)
        threshold = FLOOR * best
        a = fraction(p["native_alignment_fraction"]["old"])
        b = fraction(p["native_alignment_fraction"]["new"])
        observed = p["recovered"]["new"] / p["observed_kmers"] if p["observed_kmers"] else None
        exclusive = (p["exclusive_recovered"]["new"] / p["exclusive_kmers"]
                     if p["exclusive_kmers"] else None)
        category = classify(values["ivanka"], b, threshold, observed, exclusive)
        rows.append({"case": case, "family": native["family"], "truth": key,
                     "truth_sha256": sha(truth.encode()), "truth_length": len(truth),
                     "original_input_sha256": fingerprint, "native_seeded": native["seeded"],
                     "rival_count": len(rivals), "historical_best_rival_fraction": best,
                     "historical_best_rivals": [name for name in rivals if values[name] == best],
                     "historical_final_candidate_fraction": values["ivanka"],
                     "historical_rival_relative_threshold": threshold,
                     "native_old_alignment_fraction": a, "native_new_alignment_fraction": b,
                     "native_new_observed_recovery": observed,
                     "native_new_exclusive_recovery": exclusive, "triage": category})
    return rows


def report(ledger, native, posthoc, data):
    raw = pinned(native, NATIVE)
    post = json.loads(pinned(posthoc, POSTHOC))
    identity = validate(raw, post)
    require(identity["posthoc_completed"] == 128, "incomplete native report")
    historical = {}
    for line in pinned(ledger, LEDGER).splitlines():
        row = json.loads(line)
        require(row["id"] not in historical, "duplicate historical case")
        historical[row["id"]] = row
    require(len(historical) == 464 and CASES <= historical.keys(), "historical roster drift")
    rows = [r for case in post["cases"]
            for r in matched_case(case, historical[case["case"]], data)]
    require(len(rows) == 192, "incomplete matched truth panel")
    summaries = {"all": dict(Counter(r["triage"] for r in rows))}
    for family in sorted({r["family"] for r in rows}):
        summaries[family] = dict(Counter(r["triage"] for r in rows if r["family"] == family))
    return {"schema": "ivanka.p1.cross-context-triage.v1", "not_qualification": True,
            "scope": "historical integrated final output vs prospective raw native output; no causal inference",
            "ledger_sha256": LEDGER, "native_sha256": NATIVE, "posthoc_sha256": POSTHOC,
            "matched_cases": len(CASES), "matched_truths": len(rows),
            "rival_threshold_context": "historical successful rivals only",
            "summaries": summaries, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ledger", "native", "posthoc", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    result = report(a.ledger, a.native, a.posthoc, a.data)
    with a.output.open("x") as target:
        json.dump(result, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps(result["summaries"], sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
