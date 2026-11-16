"""Compare MiCall assembly-to-consensus stages for source-attested paired runs.

This is an evaluator-only diagnostic. Never feed its scores to an assembler,
adapter, contig selector, or any experimental source-pinned MiCall invocation.
"""
import argparse
import csv
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import mean

STAGES = {
    "native_contigs": ("unstitched_contigs.csv", "contig"),
    "remap_targets": ("remap_conseq.csv", "sequence"),
    "final_consensus": ("conseq.csv", "sequence"),
}


def digest(data):
    return sha256(data).hexdigest()


def snapshot(root, expected):
    manifest = json.loads((root / "run_manifest.json").read_text())
    marker = json.loads((root / "attempt_complete_marker.json").read_text())
    data = (root / "results.jsonl").read_bytes()
    if not data.endswith(b"\n"):
        raise ValueError("unterminated source journal")
    rows = [json.loads(line) for line in data.splitlines()]
    if (len(rows) != expected or len({row["id"] for row in rows}) != expected
            or marker["samples_attempted"] != expected
            or marker["results_sha256"] != digest(data)
            or marker["run_manifest_sha256"] != digest(
                (root / "run_manifest.json").read_bytes())
            or marker.get("ivanka_source_commit", manifest["ivanka_source_commit"])
            != manifest["ivanka_source_commit"]
            or manifest["qualified"] is not False):
        raise ValueError("incomplete or unauthenticated source-pinned journal")
    proof = {
        "manifest_sha256": digest((root / "run_manifest.json").read_bytes()),
        "journal_sha256": digest(data),
        "completion_sha256": digest((root / "attempt_complete_marker.json").read_bytes()),
        "cohort_sha256": manifest["cohort_sha256"],
        "ivanka_source_commit": manifest["ivanka_source_commit"],
        "ivanka_image_sha256": manifest["images"]["ivanka"],
    }
    return {row["id"]: row for row in rows}, proof


def stage(root, identity, name, field):
    file = root / identity / "ivanka" / name
    if not file.is_file() or file.is_symlink():
        raise ValueError(f"missing stage evidence: {file}")
    raw = file.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    if not rows or any(field not in row or row[field] is None for row in rows):
        raise ValueError(f"invalid stage sequence evidence: {file}")
    lengths = sorted((len(row[field]) for row in rows), reverse=True)
    return {"sequences": len(lengths), "max_length": lengths[0],
            "lengths": lengths, "sha256": digest(raw)}


def stages(root, identity):
    return {label: stage(root, identity, name, field)
            for label, (name, field) in STAGES.items()}


def valid_score(record, name):
    arm = record.get("ivanka", {})
    if arm.get("status") != "success":
        raise ValueError(f"non-success arm for {name}")
    score = arm.get("score")
    seconds = arm.get("seconds")
    if any(type(value) not in (int, float) or not isfinite(value)
           for value in (score, seconds)):
        raise ValueError(f"missing or nonfinite final score/runtime: {name}")
    return float(score), float(seconds)


def compare(old_root, new_root, expected):
    old, first = snapshot(old_root, expected)
    new, second = snapshot(new_root, expected)
    if first["cohort_sha256"] != second["cohort_sha256"] or old.keys() != new.keys():
        raise ValueError("different cohort or sample identities")
    if first["ivanka_source_commit"] == second["ivanka_source_commit"]:
        raise ValueError("not a source-revision comparison")
    if first["ivanka_image_sha256"] == second["ivanka_image_sha256"]:
        raise ValueError("same immutable image in both cohorts")
    rows = []
    for identity in sorted(old):
        before, after = old[identity], new[identity]
        if (before["input_sha256"] != after["input_sha256"]
                or before["truth_validation"] != after["truth_validation"]
                or before["family"] != after["family"]):
            raise ValueError(f"original source or evaluator truth differs: {identity}")
        old_score, old_seconds = valid_score(before, identity)
        new_score, new_seconds = valid_score(after, identity)
        old_stages, new_stages = stages(old_root, identity), stages(new_root, identity)
        rows.append({
            "id": identity, "family": before["family"],
            "score_before": old_score, "score_after": new_score,
            "score_delta": new_score - old_score,
            "runtime_delta_seconds": new_seconds - old_seconds,
            "before": old_stages, "after": new_stages,
            "native_max_delta": new_stages["native_contigs"]["max_length"]
            - old_stages["native_contigs"]["max_length"],
            "remap_extension_before": old_stages["remap_targets"]["max_length"]
            - old_stages["native_contigs"]["max_length"],
            "remap_extension_after": new_stages["remap_targets"]["max_length"]
            - new_stages["native_contigs"]["max_length"],
        })
    summary = {}
    for family in sorted({row["family"] for row in rows}):
        subset = [row for row in rows if row["family"] == family]
        summary[family] = {
            "cases": len(subset),
            "score_improved": sum(x["score_delta"] > 0 for x in subset),
            "score_worse": sum(x["score_delta"] < 0 for x in subset),
            "score_tied": sum(x["score_delta"] == 0 for x in subset),
            "mean_score_delta": mean(x["score_delta"] for x in subset),
            "mean_runtime_delta_seconds": mean(x["runtime_delta_seconds"]
                                               for x in subset),
        }
    return {
        "schema": "ivanka.diagnostic.stitch_stages.v1",
        "status": "DIAGNOSTIC_NOT_QUALIFICATION",
        "source_evidence": {"before": first, "after": second},
        "total": len(rows), "families": summary,
        "score_improved": sum(x["score_delta"] > 0 for x in rows),
        "score_worse": sum(x["score_delta"] < 0 for x in rows),
        "score_tied": sum(x["score_delta"] == 0 for x in rows),
        "faster": sum(x["runtime_delta_seconds"] < 0 for x in rows),
        "mean_runtime_delta_seconds": mean(x["runtime_delta_seconds"] for x in rows),
        "examples_of_largest_regression": [
            row["id"] for row in sorted(rows, key=lambda x: x["score_delta"])[:8]],
        "samples": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = compare(args.before, args.after, args.expected)
    if args.out.exists():
        raise ValueError("refuse to overwrite frozen diagnostic")
    with args.out.open("x") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("SOURCE_PINNED_STAGE_DIAGNOSTIC", report["total"],
          "regressions", report["score_worse"], "faster", report["faster"])


if __name__ == "__main__":
    main()
