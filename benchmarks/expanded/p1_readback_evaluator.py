"""Immutable readback evaluator for the P1 full-464 candidate attempt.

The evaluator reads a finished attempt root, re-verifies the frozen inputs,
the sealed summary, the exact manifest, every case receipt and the attested
historical gate, then recomputes every combined and per-truth comparison from
observed records. It never writes to the attempt root and never supplies
missing truth panels from memory or from the gate error list.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re

from .p1_full464_controller import (
    FLOOR,
    ORIGINAL_IVANKA_IMAGE,
    PINS,
    STATUS,
    complete_per_truth,
    evaluate,
    load_committed,
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
DEFAULT_COHORT = "/workspace/ivanka-synthetic-abundance15-464-20261117"
TRUTH_ERROR = re.compile(
    r"^(?P<case>[^:]+):ivanka_below_90pct_for_(?P<truth>truth_\d+)$")
COMBINED_ERROR = ":ivanka_below_90pct_best_competitor"
MISSING_ARM_ERROR = ":failed_or_unrun_assembler"
RIVALS = ("iva", "abyss", "haploflow", "megahit", "spades", "velvet")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def load_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def finite_number(value):
    """Finite numeric score; booleans are not scores."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def positive_seconds(value):
    """A comparable runtime must be a finite, strictly positive number."""
    return finite_number(value) and value > 0


def load_cohort(cohort_root, expected_hash, expected_cases):
    """Read only the hash-pinned cohort manifest for per-case input proofs."""
    path = Path(cohort_root) / "cohort.json"
    actual = sha256(path)
    if actual != expected_hash:
        raise ValueError("cohort manifest hash differs from pin")
    cohort = load_json(path)
    hashes = {entry["id"]: entry["sha256"] for entry in cohort["cases"]}
    if len(hashes) != expected_cases or cohort.get("samples") != expected_cases:
        raise ValueError("cohort does not cover the expected case count")
    return hashes, actual


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
        case_id = error.split(":", 1)[0]
        match = TRUTH_ERROR.match(error)
        if match and match.group("case") in synthetic_ids:
            truth_failures[match.group("case")].add(match.group("truth"))
        elif error.endswith(COMBINED_ERROR) and case_id in synthetic_ids:
            combined_failures.add(case_id)
        elif (error.endswith(MISSING_ARM_ERROR)
              and case_id not in synthetic_ids):
            blocked_real.add(case_id)
    return {
        "sha256": actual,
        "truth_failures": {key: sorted(value)
                           for key, value in truth_failures.items()},
        "combined_failures": sorted(combined_failures),
        "physical_blocked_cases": sorted(blocked_real),
        "observed": observed,
    }


def verify_attempt_root(root, expected_cases, *, cohort_root=DEFAULT_COHORT,
                        cohort_cases=None, cohort_hash=None, pins=None):
    """Fail closed unless summary, manifest, pins, identity and receipts agree."""
    root = Path(root).resolve()
    pins = pins or PINS
    cohort_hash = cohort_hash or pins["cohort.json"]
    if not isinstance(pins, dict) or not pins or not pins.get("cohort.json"):
        raise ValueError("run manifest pins are missing")
    summary_path = root / "attempt_summary.json"
    if not summary_path.is_file():
        raise ValueError("sealed attempt summary is missing")
    summary = load_json(summary_path)
    if (summary.get("qualified") is not False
            or summary.get("cases_attempted") != expected_cases
            or not HEX64.fullmatch(str(summary.get("result_sha256", "")))):
        raise ValueError("attempt summary is incomplete or inconsistent")
    manifest_path = root / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("run manifest is missing")
    manifest = load_json(manifest_path)
    if manifest.get("pins") != pins:
        raise ValueError("attempt manifest source pins differ from the pin")
    image = manifest.get("candidate_image")
    commit = manifest.get("candidate_source_commit")
    if (not HEX64.fullmatch(str(image)) or image == ORIGINAL_IVANKA_IMAGE
            or not HEX40.fullmatch(str(commit))):
        raise ValueError("attempt manifest candidate identity is invalid")
    results = root / "results.jsonl"
    actual = sha256(results)
    if actual != summary["result_sha256"]:
        raise ValueError("candidate results digest differs from sealed summary")
    rows = read_jsonl(results)
    if len(rows) != expected_cases or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("candidate attempt is incomplete or duplicated")
    hashes, cohort_actual = load_cohort(
        cohort_root, cohort_hash, cohort_cases or expected_cases)
    observed_ids = {row["id"] for row in rows}
    if (len(observed_ids) != expected_cases
            or not observed_ids.issubset(hashes)):
        raise ValueError("candidate cases differ from the pinned cohort")
    for row in rows:
        proof = row.get("provenance", {})
        if (proof.get("candidate_image") != image
                or proof.get("candidate_source_commit") != commit
                or proof.get("original_arms_rerun") is not False):
            raise ValueError(f"{row['id']}: candidate provenance differs")
        committed = load_committed(root / row["id"], hashes[row["id"]], image)
        if committed != row:
            raise ValueError(f"{row['id']}: case receipt differs from result row")
    return rows, actual, summary, manifest, hashes, cohort_actual


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


def attested_truth_panels(frozen, case_ids):
    """Pin each case's truth keys and identity from attested original panels."""
    panels = {}
    for case_id in sorted(case_ids):
        entries = {}
        for arm in frozen[case_id]["results"].values():
            for key, item in (arm.get("per_truth") or {}).items():
                record = (item.get("truth_sha256"), item.get("length"),
                          item.get("nominal_abundance"))
                if (not HEX64.fullmatch(str(record[0]))
                        or not isinstance(record[1], int)
                        or not finite_number(record[2])):
                    raise ValueError(f"{case_id}:{key}:invalid attested truth")
                if key in entries and entries[key] != record:
                    raise ValueError(f"{case_id}:{key}:inconsistent truth panel")
                entries[key] = record
        panels[case_id] = entries
    return panels


def truth_fraction(record):
    """Derive a comparable fraction from attested raw alignment evidence."""
    if not isinstance(record, dict):
        return None
    length = record.get("length")
    raw = record.get("score")
    if not isinstance(length, int) or length <= 0 or not finite_number(raw):
        return None
    return raw / length


def check_panel(label, panel, expected, errors):
    """Reject missing, extra or re-identified abundant-truth entries."""
    if not isinstance(panel, dict):
        errors.append(f"{label}:invalid_truth_panel")
        return
    keys = set(panel)
    if set(expected) != keys:
        errors.append(f"{label}:truth_keys_missing_or_extra")
        return
    for key in sorted(keys):
        item = panel[key]
        digest, length, abundance = expected[key]
        if (not isinstance(item, dict)
                or item.get("truth_sha256") != digest
                or item.get("length") != length
                or not finite_number(item.get("nominal_abundance"))
                or abs(item["nominal_abundance"] - abundance) > 1e-9):
            errors.append(f"{label}:truth_identity_mismatch:{key}")


def recompute_case(row, expected=None):
    """Recompute the combined floor and every abundant-truth floor afresh."""
    results = row.get("results", {})
    candidate = results.get("ivanka", {})
    rivals = {name: arm for name, arm in results.items() if name != "ivanka"}
    errors = []
    if set(rivals) != set(RIVALS):
        errors.append("wrong_rival_roster")
    if candidate.get("status") != "success" or not complete_per_truth(candidate):
        errors.append("candidate_not_success_or_panel_missing")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": []}
    if not valid_score(candidate) or not finite_number(candidate.get("seconds")):
        errors.append("candidate_invalid_score_or_seconds")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": []}
    if expected is None:
        errors.append("no_attested_truth_panel")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": []}
    check_panel("ivanka", candidate["per_truth"], expected, errors)
    available = []
    for name, arm in sorted(rivals.items()):
        if arm.get("status") != "success" or not complete_per_truth(arm):
            continue
        if not valid_score(arm) or not positive_seconds(arm.get("seconds")):
            errors.append(f"rival_invalid_score_or_seconds:{name}")
            continue
        check_panel(name, arm["per_truth"], expected, errors)
        available.append(name)
    if not positive_seconds(candidate["seconds"]):
        errors.append("candidate_invalid_seconds")
    if errors:
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [],
                "available_rivals": sorted(available)}
    if not available:
        errors.append("no_complete_rival_for_comparison")
        return {"id": row["id"], "family": row.get("family"),
                "errors": errors, "truths": [], "available_rivals": []}
    best_combined = max(rivals[name]["score"] for name in available)
    combined_pass = candidate["score"] + 1e-7 >= FLOOR * best_combined
    if not combined_pass:
        errors.append("below_90pct_best_available_rival")
    truths = []
    panels = {name: rivals[name]["per_truth"] for name in available}
    for truth_key in sorted(expected):
        record = candidate["per_truth"][truth_key]
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
                      gate_path=DEFAULT_GATE_JSON,
                      cohort_root=DEFAULT_COHORT, expected_cases=464,
                      frozen_cases=None, cohort_cases=None,
                      frozen_hash=None, gate_hash=None, cohort_hash=None,
                      pins=None):
    """Validate an immutable attempt and recompute every P1 comparison."""
    pins = pins or PINS
    frozen_hash = frozen_hash or pins["phase-synthetic464/results.jsonl"]
    gate_hash = gate_hash or GATE_JSON_SHA256
    cohort_hash = cohort_hash or pins["cohort.json"]
    rows, results_hash, summary, manifest, case_hashes, cohort_actual = (
        verify_attempt_root(root, expected_cases, cohort_root=cohort_root,
                            cohort_cases=cohort_cases,
                            cohort_hash=cohort_hash, pins=pins))
    frozen, frozen_actual = load_frozen(
        frozen_path, frozen_hash, frozen_cases or expected_cases)
    joined, identity_errors = join_frozen_arms(rows, frozen, frozen_actual)
    gate = load_attested_gate(gate_path, gate_hash, set(frozen))
    base = evaluate(joined)
    panels = attested_truth_panels(frozen, set(frozen))
    recomputed = [recompute_case(row, panels.get(row["id"])) for row in joined]
    family = defaultdict(Counter)
    for case in recomputed:
        for error in case["errors"]:
            family[case.get("family") or "unknown"][error] += 1
    observed = {row["id"] for row in rows}
    missing_cases = sorted(set(case_hashes) - observed)
    base_by_id = {case["id"]: case for case in base["per_case"]}
    failed_rivals = [case_id for case_id, case in base_by_id.items()
                     if case.get("failed_rivals")]
    incomplete_rivals = [case_id for case_id, case in base_by_id.items()
                         if case.get("incomplete_rivals")]
    wrong_roster = [case_id for case_id, case in base_by_id.items()
                    if "wrong_rival_roster" in case.get("errors", [])]
    candidate_failures = [case["id"] for case in recomputed if case["errors"]]
    full_seven_reasons = []
    if gate["physical_blocked_cases"]:
        full_seven_reasons.append("physical_full_seven_failed_arms")
    if missing_cases:
        full_seven_reasons.append("synthetic_missing_cases")
    if failed_rivals:
        full_seven_reasons.append("synthetic_failed_rival_arms")
    if incomplete_rivals:
        full_seven_reasons.append("synthetic_incomplete_rival_arms")
    if wrong_roster:
        full_seven_reasons.append("synthetic_wrong_rival_roster")
    if candidate_failures:
        full_seven_reasons.append("synthetic_candidate_or_evaluation_failures")
    if identity_errors:
        full_seven_reasons.append("frozen_arm_identity_failure")
    return {
        "schema": "ivanka.p1.readback-evaluation.v1",
        "status": STATUS,
        "qualification_claim": "NONE",
        "attempt_results_sha256": results_hash,
        "frozen_results_sha256": frozen_actual,
        "attested_gate_sha256": gate["sha256"],
        "cohort_manifest_sha256": cohort_actual,
        "receipt_integrity": {"cases": len(rows), "all_verified": True,
                              "summary_sha256": sha256(
                                  Path(root) / "attempt_summary.json")},
        "identity_errors": identity_errors,
        "source_pins": pins,
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
        "full_seven_blocked_counts": {
            "missing_cases": len(missing_cases),
            "cases_with_failed_rivals": len(failed_rivals),
            "cases_with_incomplete_rivals": len(incomplete_rivals),
            "cases_with_wrong_roster": len(wrong_roster),
            "candidate_failure_cases": len(candidate_failures),
            "physical_failed_arms": len(gate["physical_blocked_cases"]),
        },
        "pass": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--frozen-results", type=Path, default=Path(DEFAULT_FROZEN))
    parser.add_argument("--gate-json", type=Path, default=Path(DEFAULT_GATE_JSON))
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_COHORT))
    parser.add_argument("--frozen-cases", type=int)
    parser.add_argument("--cohort-cases", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve()
    if output == root or root in output.parents:
        raise ValueError("evaluation output must be outside the attempt root")
    report = evaluate_readback(root, frozen_path=args.frozen_results,
                               gate_path=args.gate_json,
                               cohort_root=args.data,
                               frozen_cases=args.frozen_cases,
                               cohort_cases=args.cohort_cases)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("P1_READBACK", STATUS, "cases",
          report["independent_evaluator"]["cases"],
          "full_seven_blocked", not report["full_seven_complete"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
