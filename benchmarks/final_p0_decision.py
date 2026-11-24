#!/usr/bin/env python3
"""Fail-closed final physical P0 decision reconciliation.

This tool maps the read-only frozen-original audit evidence (independently
verified exact score readback plus hash-attested checkpoint metrics) onto one
explicit decision state. It changes no threshold, never converts a missing or
failed arm into a win, and never implies the expanded 464-synthetic or clinical
completion claim. Evidence categories are kept distinct: malformed/invalid
evidence is an integrity failure, while a complete, valid cohort that misses a
numerical criterion is a measured scientific failure.

All proof obligations are explicit checks that return a state or append a
reason; the module deliberately uses no ``assert`` so behaviour is identical
under ``python -O``. Output contains only counts, category names and the public
pinned digests - never a sample identifier.

Input is either a previously generated PR433 audit report (``--report``) or a
fresh read-only audit run with exact readback enabled (``--root``,
``--frozen-root``, ``--projects-json``, ``--hxb2-fasta``).
"""

import argparse
import json
import math
from pathlib import Path

import independent_frozen_psi_audit as audit

SCHEMA = "ivanka.p0.final-physical-decision.v1"

INCOMPLETE_COHORT = "INCOMPLETE_COHORT"
INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
PER_CASE_FLOOR_FAILURE = "PER_CASE_FLOOR_FAILURE"
NO_PAIRED_EVIDENCE = "NO_PAIRED_EVIDENCE"
SIGNED_POWER_FAILURE_AT_R_ZERO = "SIGNED_POWER_FAILURE_AT_R_ZERO"
SIGNED_POWER_FAILURE_HIGH_R_TAIL = "SIGNED_POWER_FAILURE_HIGH_R_TAIL"
SIGNED_POWER_FAILURE_INTERIOR = "SIGNED_POWER_FAILURE_INTERIOR"
STRICT_PAIRED_SUCCESS_MISSING_ARMS = "STRICT_PAIRED_DIAGNOSTIC_SUCCESS_MISSING_RIVAL_ARMS"
ORIGINAL_IVA_GATE_PASS = "ORIGINAL_IVA_GATE_PASS"
PHYSICAL_FULL_SEVEN_PASS = "PHYSICAL_FULL_SEVEN_ALL_R_PASS_NO_EXPANDED_CLAIM"

_FAILURE_STATE = {
    "fails_nonpositive_at_r_zero": SIGNED_POWER_FAILURE_AT_R_ZERO,
    "fails_negative_high_r_tail": SIGNED_POWER_FAILURE_HIGH_R_TAIL,
    "fails_interior_zero_or_negative": SIGNED_POWER_FAILURE_INTERIOR,
}
_FAILURE_PRIORITY = (
    SIGNED_POWER_FAILURE_AT_R_ZERO,
    SIGNED_POWER_FAILURE_HIGH_R_TAIL,
    SIGNED_POWER_FAILURE_INTERIOR,
)
_AXES = ("score", "runtime")
_KNOWN_VERDICTS = frozenset((
    "dominates_on_observed_pairs", "no_paired_successes",
    "fails_nonpositive_at_r_zero", "fails_negative_high_r_tail",
    "fails_interior_zero_or_negative",
))


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _reject(reasons, reason):
    """Record one anonymized integrity reason. No exception short-circuiting."""
    if reason not in reasons:
        reasons.append(reason)


def verdict_from_proof(proof, paired):
    """Re-derive an axis verdict from its proof, independently of the label.

    Mirrors ``independent_frozen_psi_audit.signed_power`` so a report whose
    label was altered or copied from another cohort is rejected instead of
    being trusted as a success.
    """
    if not paired:
        return "no_paired_successes"
    if proof.get("positive_all_nonnegative") is True:
        return "dominates_on_observed_pairs"
    psi0 = proof.get("psi0")
    if _is_number(psi0) and psi0 <= 0:
        return "fails_nonpositive_at_r_zero"
    if proof.get("psi_at_positive_infinity") == "-inf":
        return "fails_negative_high_r_tail"
    return "fails_interior_zero_or_negative"


def _failure_state(verdict, proof):
    """Map a verified axis verdict onto the most specific measured failure.

    A finite negative coefficient on the largest |p| sends Psi(r) negative as
    r grows without bound. PR433's coarse verdict labels that an interior
    failure; the reported scientific state must still identify the tail.
    """
    if verdict == "fails_nonpositive_at_r_zero":
        return SIGNED_POWER_FAILURE_AT_R_ZERO
    if verdict == "fails_negative_high_r_tail":
        return SIGNED_POWER_FAILURE_HIGH_R_TAIL
    limit = proof.get("psi_at_positive_infinity")
    if limit == "-inf" or (_is_number(limit) and limit < 0):
        return SIGNED_POWER_FAILURE_HIGH_R_TAIL
    return SIGNED_POWER_FAILURE_INTERIOR


def validate_report(report):
    """Return anonymized integrity reasons; an empty list means usable evidence."""
    reasons = []
    if not isinstance(report, dict):
        return ["report_not_object"]
    if report.get("schema") != audit.SCHEMA:
        _reject(reasons, "audit_schema_drift")
    if report.get("qualification_claim") != "NONE":
        _reject(reasons, "audit_claim_not_none")
    pinned = report.get("pinned")
    if not isinstance(pinned, dict):
        _reject(reasons, "pinned_missing")
    else:
        if pinned.get("image_sha256") != audit.IMAGE:
            _reject(reasons, "pinned_image_drift")
        if pinned.get("manifest_sha256") != audit.MANIFEST:
            _reject(reasons, "pinned_manifest_drift")
        if pinned.get("panel_sha256") != audit.PANEL:
            _reject(reasons, "pinned_panel_drift")
    if report.get("expected_cases") != audit.EXPECTED_CASES:
        _reject(reasons, "expected_cases_drift")
    attested = report.get("attested_finished_cases")
    if not _is_int(attested) or not 0 <= attested <= audit.EXPECTED_CASES:
        _reject(reasons, "attested_count_invalid")
        attested = None
    # Exact score readback is mandatory for a final decision: checkpoint
    # metrics alone leave a trust dependency on the controller's score.
    if report.get("candidate_alignment_recomputed") is not True:
        _reject(reasons, "exact_score_readback_absent")
    attestation = report.get("attestation")
    if not isinstance(attestation, dict):
        _reject(reasons, "attestation_missing")
    else:
        if attested is not None and attestation.get("finished_with_both_files") != attested:
            _reject(reasons, "attestation_count_mismatch")
        if attestation.get("rejection_reasons"):
            _reject(reasons, "attestation_rejections_present")
    complete = attested == audit.EXPECTED_CASES
    expected_scope = "COMPLETE_COHORT_DIAGNOSTIC" if complete else "EXPLICITLY_PARTIAL"
    expected_status = ("COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION" if complete
                       else "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE")
    if report.get("scope") != expected_scope or report.get("status") != expected_status:
        _reject(reasons, "scope_status_mismatch")
    floors = report.get("observed_quality_floor_failures")
    if not isinstance(floors, dict):
        _reject(reasons, "floor_counts_missing")
    else:
        for key in ("best_available", "iva"):
            value = floors.get(key)
            if not _is_int(value) or value < 0 or value > (attested if attested is not None else audit.EXPECTED_CASES):
                _reject(reasons, "floor_counts_invalid")
    comparators = report.get("comparators")
    if not isinstance(comparators, dict):
        return reasons + ["comparators_missing"]
    if set(comparators) != set(audit.RIVALS):
        _reject(reasons, "comparator_roster_drift")
    expected_full_cohort = complete
    for tool in audit.RIVALS:
        row = comparators.get(tool)
        if not isinstance(row, dict):
            _reject(reasons, "comparator_shape_invalid")
            expected_full_cohort = False
            continue
        paired = row.get("paired")
        if not _is_int(paired) or not 0 <= paired <= (attested if attested is not None else audit.EXPECTED_CASES):
            _reject(reasons, "paired_count_invalid")
            continue
        if paired != audit.EXPECTED_CASES:
            expected_full_cohort = False
        if row.get("missing_or_failed_total") != audit.EXPECTED_CASES - paired:
            _reject(reasons, "missing_arm_count_mismatch")
        if attested is not None:
            if row.get("unpaired_among_finished") != attested - paired:
                _reject(reasons, "unpaired_count_mismatch")
            if row.get("unfinished_cases") != audit.EXPECTED_CASES - attested:
                _reject(reasons, "unfinished_count_mismatch")
        for axis in _AXES:
            evidence = row.get(axis)
            if not isinstance(evidence, dict):
                _reject(reasons, "axis_evidence_missing")
                continue
            if evidence.get("paired") != paired:
                _reject(reasons, "axis_pair_count_mismatch")
            proof = evidence.get("proof")
            verdict = evidence.get("verdict")
            if paired == 0:
                if verdict != "no_paired_successes" or proof is not None:
                    _reject(reasons, "unpaired_axis_evidence_invalid")
                continue
            if not isinstance(proof, dict):
                _reject(reasons, "axis_proof_missing")
                continue
            # An unresolved signed-power search is inadmissible evidence, not a
            # measured scientific failure; never report it as one.
            if proof.get("proof_incomplete") is True:
                _reject(reasons, "signed_power_proof_unresolved")
            if verdict not in _KNOWN_VERDICTS:
                _reject(reasons, "verdict_unknown")
            elif verdict != verdict_from_proof(proof, paired):
                _reject(reasons, "verdict_proof_mismatch")
            counts = [proof.get(key) for key in ("gains", "losses", "ties")]
            psi0 = proof.get("psi0")
            if not all(_is_int(v) and v >= 0 for v in counts) or sum(counts) != paired:
                _reject(reasons, "proof_counts_invalid")
            elif not _is_number(psi0) or not math.isclose(
                psi0, (counts[0] - counts[1]) / paired, rel_tol=0, abs_tol=1e-15
            ):
                _reject(reasons, "psi0_invalid")
            if not isinstance(proof.get("positive_all_nonnegative"), bool):
                _reject(reasons, "proof_status_invalid")
            if proof.get("positive_all_nonnegative") is True and (
                not _is_number(psi0) or psi0 <= 0
                or proof.get("zeros_nonnegative") != []
                or proof.get("proof_incomplete") is True
                or "negative_witness_r" in proof
                or proof.get("psi_at_positive_infinity") == "-inf"
                or (_is_number(proof.get("psi_at_positive_infinity"))
                    and proof["psi_at_positive_infinity"] < 0)
            ):
                _reject(reasons, "positive_proof_contradiction")
            limit = proof.get("psi_at_positive_infinity")
            # A zero-slope largest magnitude is reported as the exact signed
            # count divided by n, not as a symbolic string.
            if limit not in ("0", "+inf", "-inf") and (
                not _is_number(limit)
            ):
                _reject(reasons, "high_r_limit_invalid")
    if report.get("full_cohort_eligible") is not expected_full_cohort:
        _reject(reasons, "full_cohort_flag_mismatch")
    return reasons


def _result(state, report, reasons=None, failures=None):
    comparators = report.get("comparators") if isinstance(report, dict) else None
    attested = report.get("attested_finished_cases") if isinstance(report, dict) else None
    missing = []
    if isinstance(comparators, dict):
        for tool in audit.RIVALS:
            row = comparators.get(tool)
            if isinstance(row, dict) and _is_int(row.get("paired")):
                paired = row["paired"]
                if paired < audit.EXPECTED_CASES:
                    missing.append({"rival": tool, "paired": paired,
                                    "missing_total": audit.EXPECTED_CASES - paired})
    floors = report.get("observed_quality_floor_failures") if isinstance(report, dict) else None
    return {
        "schema": SCHEMA,
        "decision": state,
        "decision_scope": "PHYSICAL_ORIGINAL_198_ONLY",
        "cohort": {"attested_finished_cases": attested,
                   "expected_cases": audit.EXPECTED_CASES,
                   "complete": attested == audit.EXPECTED_CASES},
        "integrity_reasons": reasons or [],
        "per_case_floor_failures": floors if isinstance(floors, dict) else None,
        "signed_power_failures": failures or [],
        "missing_rival_arms": missing,
        "gates": {
            "original_iva_gate_pass": False,
            "strict_paired_diagnostic_pass": False,
            "physical_full_seven_complete": False,
            "physical_full_seven_pass": False,
            "expanded_464_synthetic_claim": False,
        },
        "expanded_claim": "NONE",
        "qualification_claim": "NONE",
        "contains_sample_identifiers": False,
    }


def decide(report):
    """Map a validated audit report onto exactly one fail-closed decision."""
    reasons = validate_report(report)
    if reasons:
        return _result(INTEGRITY_FAILURE, report, reasons=reasons)
    attested = report["attested_finished_cases"]
    if attested != audit.EXPECTED_CASES:
        return _result(INCOMPLETE_COHORT, report)
    floors = report["observed_quality_floor_failures"]
    comparators = report["comparators"]

    def complete(tool):
        return comparators[tool]["paired"] == audit.EXPECTED_CASES

    def dominates(tool):
        return all(comparators[tool][axis]["verdict"] == "dominates_on_observed_pairs"
                   for axis in _AXES)

    iva_gate = complete("iva") and dominates("iva") and floors["iva"] == 0
    all_complete = all(complete(tool) for tool in audit.RIVALS)
    all_dominate = all(dominates(tool) for tool in audit.RIVALS)
    floor_pass = floors["best_available"] == 0 and floors["iva"] == 0
    failures = []
    for tool in audit.RIVALS:
        row = comparators[tool]
        for axis in _AXES:
            evidence = row[axis]
            if evidence["verdict"] == "no_paired_successes":
                failures.append({"rival": tool, "axis": axis,
                                 "verdict": evidence["verdict"]})
            elif evidence["verdict"] in _FAILURE_STATE:
                failures.append({
                    "rival": tool,
                    "axis": axis,
                    "verdict": evidence["verdict"],
                    "state": _failure_state(evidence["verdict"], evidence["proof"]),
                    "psi0": evidence["proof"]["psi0"],
                    "high_r_limit": evidence["proof"]["psi_at_positive_infinity"],
                })
    if not floor_pass:
        state = PER_CASE_FLOOR_FAILURE
    elif any(item["verdict"] == "no_paired_successes" for item in failures):
        state = NO_PAIRED_EVIDENCE
    elif failures:
        state = next(state for state in _FAILURE_PRIORITY
                     if any(item.get("state") == state for item in failures))
    elif all_complete and all_dominate:
        state = PHYSICAL_FULL_SEVEN_PASS
    elif iva_gate:
        state = ORIGINAL_IVA_GATE_PASS
    else:
        state = STRICT_PAIRED_SUCCESS_MISSING_ARMS
    result = _result(state, report, failures=failures)
    result["gates"] = {
        "original_iva_gate_pass": iva_gate,
        "strict_paired_diagnostic_pass": all_dominate and floor_pass,
        "physical_full_seven_complete": all_complete,
        "physical_full_seven_pass": all_complete and all_dominate and floor_pass,
        "expanded_464_synthetic_claim": False,
    }
    return result


def from_root(root, frozen_root, projects_json, hxb2_fasta):
    """Run the read-only audit with exact readback, then reconcile its report."""
    references = audit.load_scoring_panel(projects_json, hxb2_fasta, audit.PANEL)
    return decide(audit.diagnose(Path(root), Path(frozen_root), references=references))


def self_test():
    """Explicit no-assert checks of the decision ladder on synthetic reports."""
    import copy

    import independent_frozen_psi_audit as src

    def check(condition, label):
        if not condition:
            raise RuntimeError("self-test failed: " + label)

    def report_for(deltas, *, attested=audit.EXPECTED_CASES):
        comparators = {}
        for tool in audit.RIVALS:
            axis_values = deltas.get(tool, {"score": [1, 1], "runtime": [1, 1]})
            comparators[tool] = {
                "paired": len(axis_values["score"]),
                "unpaired_among_finished": attested - len(axis_values["score"]),
                "unfinished_cases": audit.EXPECTED_CASES - attested,
                "missing_or_failed_total": audit.EXPECTED_CASES - len(axis_values["score"]),
                "score": src.signed_power(axis_values["score"]),
                "runtime": src.signed_power(axis_values["runtime"]),
            }
        complete = attested == audit.EXPECTED_CASES
        return {
            "schema": audit.SCHEMA,
            "scope": "COMPLETE_COHORT_DIAGNOSTIC" if complete else "EXPLICITLY_PARTIAL",
            "attested_finished_cases": attested,
            "expected_cases": audit.EXPECTED_CASES,
            "observed_quality_floor_failures": {"best_available": 0, "iva": 0},
            "attestation": {"finished_with_both_files": attested, "rejection_reasons": {}},
            "candidate_alignment_recomputed": True,
            "pinned": {"image_sha256": audit.IMAGE, "manifest_sha256": audit.MANIFEST,
                       "panel_sha256": audit.PANEL},
            "comparators": comparators,
            "full_cohort_eligible": complete and all(row["paired"] == audit.EXPECTED_CASES
                                                    for row in comparators.values()),
            "status": ("COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION" if complete
                       else "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE"),
            "qualification_claim": "NONE",
        }

    full = {tool: {"score": [1] * audit.EXPECTED_CASES,
                   "runtime": [1] * audit.EXPECTED_CASES} for tool in audit.RIVALS}
    result = decide(report_for(full))
    check(result["decision"] == PHYSICAL_FULL_SEVEN_PASS, "full seven pass")
    check(result["gates"]["expanded_464_synthetic_claim"] is False, "no expanded claim")
    partial = report_for(
        {tool: {"score": [1] * (audit.EXPECTED_CASES - 1),
                "runtime": [1] * (audit.EXPECTED_CASES - 1)} for tool in audit.RIVALS},
        attested=audit.EXPECTED_CASES - 1,
    )
    check(decide(partial)["decision"] == INCOMPLETE_COHORT, "incomplete")
    tampered = report_for(full)
    tampered["candidate_alignment_recomputed"] = False
    check(decide(tampered)["decision"] == INTEGRITY_FAILURE, "readback absent")
    tied = copy.deepcopy(full)
    tied["iva"] = {"score": [0, 0], "runtime": [1, 1]}
    check(decide(report_for(tied))["decision"] == SIGNED_POWER_FAILURE_AT_R_ZERO, "exact ties")
    finite_tail = copy.deepcopy(full)
    finite_tail["abyss"] = {"score": [1, -1, -1, 0.5, 0.5, 0.5, 0.5],
                            "runtime": [1] * 7}
    check(decide(report_for(finite_tail))["decision"] == SIGNED_POWER_FAILURE_HIGH_R_TAIL,
          "finite negative high-r limit")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="read-only audited case root")
    parser.add_argument("--frozen-root", type=Path, help="read-only frozen seven root")
    parser.add_argument("--projects-json", type=Path, help="pinned MiCall reference catalog")
    parser.add_argument("--hxb2-fasta", type=Path, help="pinned HXB2 FASTA")
    parser.add_argument("--report", type=Path, help="previously generated PR433 audit JSON")
    parser.add_argument("--out", type=Path, help="new output file (never inside an audited root)")
    parser.add_argument("--self-test", action="store_true", help="synthetic decision checks only")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("SELF_TEST_OK")
        return 0
    if args.report:
        if any((args.root, args.frozen_root, args.projects_json, args.hxb2_fasta)):
            parser.error("--report is mutually exclusive with live-root options")
        try:
            report = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            result = _result(INTEGRITY_FAILURE, None,
                             reasons=["report_unreadable_or_malformed"])
        else:
            result = decide(report)
    else:
        if not all((args.root, args.frozen_root, args.projects_json, args.hxb2_fasta)):
            parser.error("--report or all four readback/root options are required")
        try:
            result = from_root(args.root, args.frozen_root, args.projects_json, args.hxb2_fasta)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError):
            result = _result(INTEGRITY_FAILURE, None,
                             reasons=["root_evidence_unreadable_or_malformed"])
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        resolved = args.out.resolve()
        if any(resolved.is_relative_to(root.resolve()) for root in (args.root, args.frozen_root)
               if root is not None):
            parser.error("--out must be outside both audited roots")
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")
    print("P0_FINAL_DECISION", result["decision"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
