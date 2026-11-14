"""Fail-closed 198-real + 400-synthetic, seven-assembler qualification gate.

All arms use the same final MAX local-alignment score. Qualification
requires full evidence from every assembler and both sample cohorts.
"""
import argparse
import json
import math
from pathlib import Path
import sys

from .adapters import ASSEMBLERS
from .synthetic import FAMILIES

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psi_acceptance import summarize as psi  # noqa: E402

BASELINES = tuple(name for name in ASSEMBLERS if name != "ivanka")
SCORE_FLOOR = 0.90
MAX_WALL = 1800
# The gate scores downstream MiCall output, never the assembler's FASTA.
SCORE_ORIGIN = "micall_final_max_reference_panel_v1"
SCORE_ORIGINS = {"real": SCORE_ORIGIN, "synthetic": SCORE_ORIGIN}
TIMING_ORIGIN = "micall_in_container_monotonic_v1"
TRUTH_SCHEMA = "ivanka.hxb2_truth_validation.v1"
TRUTH_SCHEMAS = {TRUTH_SCHEMA, "ivanka.hxb2_truth_validation.v2"}


def eligible_truth(row):
    """Require a pinned validator report from HXB2-derived synthetic input.

    A declared hash alone is not a proof of truth ancestry; the source
    validator and signed inputs must be independently checked externally.
    """
    proof = row.get("truth_validation")
    return (isinstance(proof, dict)
            and proof.get("schema") in TRUTH_SCHEMAS
            and proof.get("valid") is True
            and all(isinstance(proof.get(key), str)
                    and len(proof[key]) == 64
                    and all(c in "0123456789abcdef" for c in proof[key])
                    for key in ("cohort_sha256", "verification_sha256")))


def finite_positive(number):
    return (type(number) in (int, float) and math.isfinite(number)
            and number > 0)


def summarize_gate(records, *, real_count=198, synthetic_seeds=16,
                   families=FAMILIES):
    """Zero missing tools, zero missing samples, zero hidden score substitutions."""
    records = list(records)
    synthetic_count = synthetic_seeds * len(families)
    expected = {"real": real_count, "synthetic": synthetic_count}
    report = {"schema": "ivanka.expanded.seven_way.v2", "pass": False,
              "assemblers": list(ASSEMBLERS), "expected": expected,
              "families_expected": list(families), "errors": [],
              "comparisons": {}, "worst_case_floor": SCORE_FLOOR,
              "score_origins": SCORE_ORIGINS, "timing_origin": TIMING_ORIGIN,
              "synthetic_truth_schema": TRUTH_SCHEMA}
    errors = report["errors"]
    ids = set()
    groups = {"real": [], "synthetic": []}
    family_counts = {}
    for row in records:
        if not isinstance(row, dict):
            errors.append("invalid_row")
            continue
        name, cohort = row.get("id"), row.get("cohort")
        if not isinstance(name, str) or not name or name in ids:
            errors.append("duplicate_or_missing_sample_id")
            continue
        ids.add(name)
        if cohort not in groups:
            errors.append(name + ":unknown_cohort")
            continue
        groups[cohort].append(row)
        if cohort == "synthetic":
            family = row.get("family")
            family_counts[family] = family_counts.get(family, 0) + 1
    proofs = {
        json.dumps(row.get("truth_validation"), sort_keys=True)
        for row in groups["synthetic"]
    }
    if len(proofs) > 1:
        errors.append("synthetic:mixed_truth_cohorts")
    elif proofs:
        proof = groups["synthetic"][0].get("truth_validation")
        if isinstance(proof, dict) and proof.get("schema") in TRUTH_SCHEMAS:
            report["synthetic_truth_schema"] = proof["schema"]
    for cohort, count in expected.items():
        if len(groups[cohort]) != count:
            errors.append(f"{cohort}:expected_{count}_observed_{len(groups[cohort])}")
    for family in families:
        if family_counts.get(family) != synthetic_seeds:
            errors.append(f"synthetic_family_{family}:expected_{synthetic_seeds}")
    if set(family_counts) != set(families):
        errors.append("unexpected_synthetic_family")
    for cohort, rows in groups.items():
        valid = []
        fingerprints = {tool: set() for tool in ASSEMBLERS}
        for row in rows:
            name = row["id"]
            values = row.get("results")
            if not isinstance(values, dict) or set(values) != set(ASSEMBLERS):
                errors.append(f"{name}:incomplete_assembler_matrix")
                continue
            if not isinstance(row.get("input_sha256"), str) or len(row["input_sha256"]) < 16:
                errors.append(f"{name}:missing_input_provenance")
                continue
            if cohort == "synthetic" and not eligible_truth(row):
                errors.append(f"{name}:missing_verified_HXB2_truth")
                continue
            if any(not isinstance(x, dict) or x.get("status") != "success"
                   for x in values.values()):
                errors.append(f"{name}:failed_or_unrun_assembler")
                continue
            if any(x.get("score_origin") != SCORE_ORIGINS[cohort]
                   or x.get("timing_origin") != TIMING_ORIGIN
                   for x in values.values()):
                errors.append(f"{name}:not_final_MiCall_output_or_timing")
                continue
            if any(not isinstance(x.get("sha256"), str)
                   or len(x["sha256"]) != 64
                   or any(c not in "0123456789abcdef" for c in x["sha256"])
                   for x in values.values()):
                errors.append(f"{name}:unversioned_assembler")
                continue
            if any(not (finite_positive(x.get("seconds"))
                        and x["seconds"] <= MAX_WALL
                        and type(x.get("score")) in (int, float)
                        and math.isfinite(x["score"]) and x["score"] >= 0)
                   for x in values.values()):
                errors.append(f"{name}:invalid_score_or_runtime")
                continue
            highest = max(values[other]["score"] for other in BASELINES)
            if values["ivanka"]["score"] < SCORE_FLOOR * highest:
                errors.append(f"{name}:ivanka_below_90pct_best_competitor")
            for tool in ASSEMBLERS:
                fingerprints[tool].add(values[tool]["sha256"])
            valid.append(row)
        for tool, digests in fingerprints.items():
            if len(digests) > 1:
                errors.append(f"{cohort}:{tool}:executable_changed_across_samples")
        if len(valid) != expected[cohort]:
            errors.append(f"{cohort}:incomplete_valid_matrix")
            continue
        report["comparisons"][cohort] = {}
        for other in BASELINES:
            score_delta = [x["results"]["ivanka"]["score"] -
                           x["results"][other]["score"] for x in valid]
            time_delta = [x["results"][other]["seconds"] -
                          x["results"]["ivanka"]["seconds"] for x in valid]
            try:
                score, runtime = psi(score_delta), psi(time_delta)
                passes = (score["positive_all_nonnegative"]
                          and runtime["positive_all_nonnegative"])
            except ValueError:
                errors.append(f"{cohort}:{other}:unresolved_psi")
                continue
            report["comparisons"][cohort][other] = {
                "pass": passes, "score_psi": score, "runtime_psi": runtime,
            }
            if not passes:
                errors.append(f"{cohort}:{other}:psi_not_positive_for_all_r")
    report["observed"] = {name: len(rows) for name, rows in groups.items()}
    report["pass"] = not errors and all(
        x["pass"] for c in report["comparisons"].values() for x in c.values()
    ) and len(report["comparisons"]) == 2
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_jsonl", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    with args.results_jsonl.open() as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    result = summarize_gate(records)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print("EXPANDED_SEVEN_WAY_PASS" if result["pass"]
          else "EXPANDED_SEVEN_WAY_NOT_PASSED",
          json.dumps({"observed": result["observed"],
                      "errors": result["errors"][:15]}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
