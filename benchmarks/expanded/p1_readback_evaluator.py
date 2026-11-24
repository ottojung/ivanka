"""Immutable readback evaluator for the P1 full-464 candidate attempt.

The evaluator reads a finished attempt root, re-verifies the frozen inputs and
the attested historical gate, then recomputes every combined and per-truth
comparison from the observed records. It never writes to the attempt root and
never supplies missing truth panels from memory or from the gate error list.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re

from .p1_full464_controller import (
    FLOOR,
    PINS,
    STATUS,
    complete_per_truth,
    evaluate,
    sha256,
    valid_score,
)

GATE_JSON_SHA256 = (
    "11ed2369dc1a1ca6869fe11079ce2c9a9ec9bd721c185fe66cc644c636e99664"
)
DEFAULT_GATE_JSON = (
    "/workspace/micall-frozen-seven-20261117/comparator-services/"
    "final-source-bound-seven-way-gate-20261121.json"
)
DEFAULT_FROZEN = (
    "/workspace/micall-frozen-seven-20261117/phase-synthetic464/results.jsonl"
)
TRUTH_ERROR = re.compile(
    r"^(?P<case>[^:]+):ivanka_below_90pct_for_(?P<truth>truth_\d+)$")
COMBINED_ERROR = ":ivanka_below_90pct_best_competitor"
MISSING_ARM_ERROR = ":failed_or_unrun_assembler"
RIVALS = ("iva", "abyss", "haploflow", "megahit", "spades", "velvet")


def load_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def load_frozen(frozen_path, expected_hash, expected_cases):
    """Return frozen rows only after the pinned results file verifies."""
    actual = sha256(frozen_path)
    if actual != expected_hash:
        raise ValueError("frozen results hash differs from pin")
    rows = {}
    for row in read_jsonl(frozen_path):
        if row["id"] in rows:
            raise ValueError("duplicate frozen case")
        rows[row["id"]] = row
    if len(rows) != expected_cases:
        raise ValueError("frozen results do not cover the expected cohort")
    return rows, actual


def load_attested_gate(gate_path, expected_hash, synthetic_ids):
    """Extract the original gate's attested per-truth and combined misses."""
    actual = sha256(gate_path)
    if actual != expected_hash:
        raise ValueError("attested gate hash differs from pin")
    gate = load_json(gate_path)
    observed = gate.get("observed", {})
    if observed.get("synthetic") != len(synthetic_ids):
        raise ValueError("attested gate synthetic cohort size differs")
    truth_failures = defaultdict(set)
    combined_failures = set()
    blocked_real = set()
    for error in gate.get("errors", []):
        match = TRUTH_ERROR.match(error)
        if match and match.group("case") in synthetic_ids:
            truth_failures[match.group("case")].add(match.group("truth"))
        elif error.endswith(COMBINED_ERROR) and error.split(":")[0] in synthetic_ids:
            combined_failures.add(error.split(":")[0])
        elif error.endswith(MISSING_ARM_ERROR):
            blocked_real.add(error.split(":")[0])
    return {
        "sha256": actual,
        "truth_failures": {key: sorted(value)
                           for key, value in truth_failures.items()},
        "combined_failures": sorted(combined_failures),
        "physical_blocked_cases": sorted(blocked_real),
        "observed": observed,
    }


def verify_attempt_root(root, expected_cases):
    """Fail closed on an incomplete or mutated candidate attempt."""
    root = Path(root)
    results = root / "results.jsonl"
    actual = sha256(results)
    summary_path = root / "attempt_summary.json"
    if summary_path.is_file():
        summary = load_json(summary_path)
        if summary.get("result_sha256") != actual:
            raise ValueError("candidate results digest differs from summary")
    else:
        summary = {}
    rows = read_jsonl(results)
    if len(rows) != expected_cases or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("candidate attempt is incomplete or duplicated")
    manifest_path = root / "run_manifest.json"
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        pins = manifest.get("pins", {})
        if pins and pins != PINS:
            raise ValueError("attempt manifest source pins differ")
    else:
        manifest = {}
    return rows, actual, summary, manifest


def join_frozen_arms(rows, frozen, frozen_hash):
    """Attach exact frozen rival records and record any identity mismatch."""
    joined = []
    identity_errors = []
    for row in rows:
        case_id = row["id"]
        if case_id not in frozen:
            identity_errors.append(f"{case_id}:missing_frozen_case")
            continue
        results = dict(row.get("results", {}))
        if "ivanka" not in results:
            identity_errors.append(f"{case_id}:missing_candidate_arm")
        for name, arm in results.items():
            if name == "ivanka":
                continue
            proof = arm.get("reused_from", {})
            if proof.get("results_sha256") != frozen_hash or proof.get(
                    "case_id") != case_id:
                identity_errors.append(f"{case_id}:{name}:unproven_reuse")
                continue
            original = frozen[case_id]["results"].get(name)
            if original is None or {key: value for key, value in arm.items()
                                    if key != "reused_from"} != original:
                identity_errors.append(f"{case_id}:{name}:frozen_arm_changed")
        joined.append({**row, "results": results})
    return joined, identity_errors


def truth_fraction(record):
    """Derive a comparable fraction from attested raw alignment evidence."""
    length = record.get("length")
    raw = record.get("score")
    numeric = (isinstance(raw, (int, float)) and not isinstance(raw, bool)
               and math.isfinite(raw))
    if not isinstance(length, int) or length <= 0 or not numeric:
        return None
    return raw / length


def recompute_case(row):
    """Recompute the combined floor and every abundant-truth floor afresh."""
    results = row.get("results", {})
    candidate = results.get("ivanka", {})
    rivals = {name: arm for name, arm in results.items() if name != "ivanka"}
    available = [name for name, arm in rivals.items()
                 if arm.get("status") == "success" and complete_per_truth(arm)
                 and valid_score(arm)]
    errors = []
    if candidate.get("status") != "success" or not complete_per_truth(candidate):
        errors.append("candidate_not_success_or_panel_missing")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": available}
    if not valid_score(candidate):
        errors.append("candidate_missing_score")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": available}
    if not available:
        errors.append("no_complete_rival_for_comparison")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": available}
    best_combined = max(rivals[name]["score"] for name in available)
    combined_pass = candidate["score"] + 1e-7 >= FLOOR * best_combined
    if not combined_pass:
        errors.append("below_90pct_best_available_rival")
    truths = []
    panels = {name: rivals[name]["per_truth"] for name in available}
    for truth_key, record in sorted(candidate["per_truth"].items()):
        own = truth_fraction(record)
        competitor_fractions = [truth_fraction(panels[name][truth_key])
                                for name in available
                                if truth_key in panels[name]]
        competitor_fractions = [value for value in competitor_fractions
                                if value is not None]
        if own is None or not competitor_fractions:
            errors.append(f"incomplete_truth_comparison:{truth_key}")
            continue
        strongest = max(competitor_fractions)
        ratio = own / strongest if strongest > 0 else 0.0
        passes = own + 1e-7 >= FLOOR * strongest
        if not passes:
            errors.append(f"below_90pct_for_{truth_key}")
        truths.append({"truth": truth_key, "candidate_fraction": own,
                       "best_rival_fraction": strongest, "ratio": ratio,
                       "pass": passes})
    return {
        "id": row["id"], "family": row.get("family"), "errors": errors,
        "candidate_score": candidate["score"],
        "best_rival_score": best_combined, "combined_pass": combined_pass,
        "truths": truths, "available_rivals": sorted(available),
    }


def evaluate_readback(root, *, frozen_path=DEFAULT_FROZEN,
                      gate_path=DEFAULT_GATE_JSON, expected_cases=464,
                      frozen_hash=None, gate_hash=None):
    """Validate an immutable attempt and recompute every P1 comparison."""
    frozen_hash = frozen_hash or PINS["phase-synthetic464/results.jsonl"]
    gate_hash = gate_hash or GATE_JSON_SHA256
    rows, results_hash, summary, manifest = verify_attempt_root(
        root, expected_cases)
    frozen, frozen_actual = load_frozen(frozen_path, frozen_hash, expected_cases)
    joined, identity_errors = join_frozen_arms(rows, frozen, frozen_actual)
    gate = load_attested_gate(gate_path, gate_hash, set(frozen))
    base = evaluate(joined)
    recomputed = [recompute_case(row) for row in joined]
    family = defaultdict(Counter)
    for case in recomputed:
        label = case.get("family") or "unknown"
        for error in case["errors"]:
            family[label][error] += 1
    candidate_failures = [case["id"] for case in recomputed
                          if case["errors"]]
    full_seven_reasons = []
    if gate["physical_blocked_cases"]:
        full_seven_reasons.append("physical_full_seven_failed_arms")
    if candidate_failures:
        full_seven_reasons.append("synthetic_candidate_or_rival_failures")
    if identity_errors:
        full_seven_reasons.append("frozen_arm_identity_failure")
    return {
        "schema": "ivanka.p1.readback-evaluation.v1",
        "status": STATUS,
        "qualification_claim": "NONE",
        "attempt_results_sha256": results_hash,
        "frozen_results_sha256": frozen_actual,
        "attested_gate_sha256": gate["sha256"],
        "identity_errors": identity_errors,
        "source_pins": PINS,
        "attempt_summary": summary,
        "attempt_manifest_candidate": {
            "image": manifest.get("candidate_image"),
            "commit": manifest.get("candidate_source_commit"),
        },
        "independent_evaluator": base,
        "recomputed_comparisons": recomputed,
        "family_deficits": {name: dict(counts)
                            for name, counts in sorted(family.items())},
        "attested_gate_deficits": {
            "per_truth_failures": gate["truth_failures"],
            "combined_failures": gate["combined_failures"],
        },
        "all_r_psi": base["all_r_psi"],
        "full_seven_complete": not full_seven_reasons,
        "full_seven_blocked_reasons": full_seven_reasons,
        "pass": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--frozen-results", type=Path, default=Path(DEFAULT_FROZEN))
    parser.add_argument("--gate-json", type=Path, default=Path(DEFAULT_GATE_JSON))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = evaluate_readback(args.root, frozen_path=args.frozen_results,
                               gate_path=args.gate_json)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("P1_READBACK", STATUS, "cases", report["independent_evaluator"]["cases"],
          "full_seven_blocked", not report["full_seven_complete"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
