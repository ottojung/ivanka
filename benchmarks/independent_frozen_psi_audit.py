#!/usr/bin/env python3
"""Read-only independent audit of frozen-original all-r PSI evidence.

This tool re-derives the six-rival signed-power diagnostics from hash-attested
finished receipts without running an assembler, editing a threshold, or writing
to the audited root. Its verdicts are explicitly scoped to the observed paired
subset; a complete cohort still yields a diagnostic, never a qualification.

Output never contains a sample identifier: only counts, category names and the
public pinned image/manifest/panel digests.
"""

import argparse
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

import psi
from psi_acceptance import summarize

SCHEMA = "ivanka.p0.independent-frozen-original-partial-psi-audit.v1"
IMAGE = "73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b"
MANIFEST = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
PANEL = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
RIVALS = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet")
EXPECTED_CASES = 198
WALL_CAP_SECONDS = 2400
SAMPLED_RSS_CAP_BYTES = 4_000_000_000
TIMING_ORIGIN = "micall_in_container_monotonic_v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checkpoint_matches(copied, original, panel):
    """Verify status and both metric values, not just a checkpoint digest."""
    if original.get("status") != "finished":
        return False
    if original.get("failed") is True:
        return (copied.get("status") == "failed"
                and copied.get("score") is None
                and copied.get("runtime_seconds") is None)
    if original.get("failed") is not False:
        return False
    measured = original.get("measurement") or {}
    score = measured.get("score")
    seconds = measured.get("seconds")
    return (
        original.get("reference_panel_sha256") == panel
        and isinstance(score, (int, float)) and math.isfinite(score)
        and isinstance(seconds, (int, float)) and math.isfinite(seconds)
        and copied.get("status") == "success"
        and copied.get("score") == score
        and copied.get("runtime_seconds") == seconds
    )


def receipt_matches_metrics(score, receipt, planned, manifest):
    """Bind the reported runtime and RSS to the execution evidence."""
    return (
        receipt.get("source_frozen_manifest_sha256") == manifest
        and receipt.get("original_checkpoint_sha256") == planned.get("original_checkpoint_sha256")
        and receipt.get("final_conseq_sha256") == score.get("candidate_conseq_sha256")
        and receipt.get("internal_seconds") == score.get("candidate_runtime_seconds")
        and receipt.get("sampled_rss_peak_bytes") == score.get("candidate_peak_rss_bytes")
        and receipt.get("exit_code") == 0
        and receipt.get("violation") is None
        and receipt.get("original_rival_arm_recomputed") is False
        and receipt.get("valid_final_max_count", 0) > 0
    )


def recomputed_floors(score):
    """Check reported floors independently from the verified paired metrics."""
    rivals = score.get("original_rivals", {})
    peers = [r["score"] for tool, r in rivals.items()
             if tool in RIVALS and r.get("status") == "success"]
    iva = rivals.get("iva", {})
    if not peers or iva.get("status") != "success":
        return False
    value = score["candidate_score"]
    best = max(peers)
    return (
        score.get("original_best_available_rival_score") == best
        and score.get("original_iva_score") == iva["score"]
        and score.get("score_floor_90pct_best_available") is True
        and score.get("score_floor_90pct_iva") is True
        and value >= 0.90 * best
        and value >= 0.90 * iva["score"]
    )


def load_scoring_panel(projects_path, hxb2_path, expected_hash):
    """Load and verify the frozen public panel; never pass it to an assembler."""
    from Bio import SeqIO
    from reference_panel import build_reference_panel, panel_sha256

    projects = json.loads(projects_path.read_text())
    hxb2 = str(SeqIO.read(hxb2_path, "fasta").seq)
    references = build_reference_panel(projects, hxb2)
    if len(references) != 33 or panel_sha256(references) != expected_hash:
        raise ValueError("reference panel identity mismatch")
    return references


def alignment_matches(folder, score, receipt, references):
    """Recompute the frozen scoring objective from retained final MAX sequences."""
    from project_references import final_max_sequences
    from reference_panel import best_panel_alignment

    sequences = final_max_sequences(folder)
    if not sequences or len(sequences) != receipt.get("valid_final_max_count"):
        return False
    return best_panel_alignment(sequences, references)["score"] == score.get("candidate_score")


def attestation(root, frozen, image, manifest, panel, references=None):
    """Return (attested score rows, reason counts) without emitting identifiers.

    The checks mirror the frozen workflow's proof obligations but are
    reimplemented here so an error in the controller is not self-certifying.
    """
    reasons = {}
    if sha(frozen / "minimal-images.json") != manifest:
        reasons["frozen_manifest_drift"] = 1
        return [], reasons
    plan = json.loads((root / "frozen-physical-plan.json").read_text())["cases"]
    if len(plan) != EXPECTED_CASES:
        reasons["plan_size_not_198"] = 1
        return [], reasons
    planned = {row["sample_sha256"]: row for row in plan}
    if len(planned) != EXPECTED_CASES:
        return [], {"duplicate_plan_keys": 1}
    cases_root = root / "physical-cases"
    rows, finished = [], 0
    for folder in sorted(cases_root.iterdir()):
        if not folder.is_dir():
            continue
        score_path = folder / "posthoc_score.json"
        receipt_path = folder / "prospective-execution.json"
        if not (score_path.is_file() and receipt_path.is_file()):
            continue
        finished += 1
        key = folder.name
        score = json.loads(score_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        planned_row = planned.get(key)
        checks = {
            "case_key_mismatch": planned_row is not None and score.get("case_sha256") == key,
            "image_drift": score.get("candidate_image_sha256") == image,
            "panel_drift": score.get("reference_panel_sha256") == panel,
            "receipt_sha_mismatch": score.get("candidate_execution_receipt_sha256") == sha(receipt_path),
            "conseq_sha_mismatch": score.get("candidate_conseq_sha256") == sha(folder / "conseq.csv"),
            "status_not_success": receipt.get("status") == "success",
            "receipt_image_drift": receipt.get("candidate_image_id") == image,
            "receipt_key_mismatch": receipt.get("sample_sha256") == key,
            "wall_cap_exceeded": receipt.get("wall_seconds", math.inf) <= WALL_CAP_SECONDS,
            "rss_cap_exceeded": receipt.get("sampled_rss_peak_bytes", math.inf) <= SAMPLED_RSS_CAP_BYTES,
            "timing_origin_drift": receipt.get("timing_origin") == TIMING_ORIGIN,
            "score_floor_fail": bool(score.get("score_floor_90pct_best_available")
                                     and score.get("score_floor_90pct_iva")),
            "nonfinite_metric": (math.isfinite(score.get("candidate_score", math.nan))
                                 and math.isfinite(score.get("candidate_runtime_seconds", math.nan))),
        }
        rivals = score.get("original_rivals", {})
        checks["original_ivanka_checkpoint_drift"] = (
            planned_row is not None
            and rivals.get("ivanka", {}).get("checkpoint_sha256") == planned_row.get("original_checkpoint_sha256"))
        checks["execution_metric_drift"] = (
            planned_row is not None and receipt_matches_metrics(score, receipt, planned_row, manifest))
        for tool in ("ivanka",) + RIVALS:
            checkpoint = frozen / "phase-real198" / tool / "checkpoints" / (key + ".json")
            copied = rivals.get(tool, {})
            original = json.loads(checkpoint.read_text())
            checks["checkpoint_drift_" + tool] = copied.get("checkpoint_sha256") == sha(checkpoint)
            checks["checkpoint_metric_drift_" + tool] = (
                planned_row is not None
                and original.get("sample") == planned_row.get("sample")
                and checkpoint_matches(copied, original, panel))
        if all(checks.values()):
            checks["recomputed_floor_fail"] = recomputed_floors(score)
            if references is not None:
                checks["candidate_alignment_drift"] = alignment_matches(folder, score, receipt, references)
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            for name in failed:
                reasons[name] = reasons.get(name, 0) + 1
            continue
        rows.append(score)
    return rows, {"finished_with_both_files": finished, "rejection_reasons": reasons}


def tail_profile(values):
    """Describe the largest-magnitude behaviour of a signed-power sum."""
    terms = psi.grouped_terms([Decimal(str(value)) for value in values])
    if not terms:
        return {"all_zero_deltas": True, "min_tail_count": None, "top_net_count": None}
    tail, min_tail, min_magnitude = Decimal(0), None, None
    for log_magnitude, count in reversed(terms):
        tail += count
        if min_tail is None or tail < min_tail:
            min_tail, min_magnitude = tail, log_magnitude
    return {
        "all_zero_deltas": False,
        "distinct_magnitudes": len(terms),
        "min_tail_count": int(min_tail),
        "min_tail_magnitude": float(min_magnitude.exp()),
        "top_magnitude": float(terms[-1][0].exp()),
        "top_net_count": int(terms[-1][1]),
        "max_loss": float(min(values)),
        "max_gain": float(max(values)),
    }


def signed_power(values):
    """Signed-power evidence on the observed pairs, never a gate verdict."""
    if not values:
        return {"paired": 0, "verdict": "no_paired_successes", "proof": None}
    proof = summarize(values, search_roots=True)
    profile = tail_profile(values)
    if proof["positive_all_nonnegative"]:
        verdict = "dominates_on_observed_pairs"
    elif proof["psi0"] <= 0:
        verdict = "fails_nonpositive_at_r_zero"
    elif proof["psi_at_positive_infinity"] == "-inf":
        verdict = "fails_negative_high_r_tail"
    else:
        verdict = "fails_interior_zero_or_negative"
    return {"paired": len(values), "verdict": verdict, "proof": proof, "tail": profile}


def cohort_status(attested, comparators):
    """Separate cohort completeness from rival-arm completeness."""
    complete = attested == EXPECTED_CASES
    full_cohort = complete and all(item["paired"] == EXPECTED_CASES
                                   for item in comparators.values())
    status = ("COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION" if complete
              else "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE")
    return complete, full_cohort, status


def diagnose(root, frozen, image=IMAGE, manifest=MANIFEST, panel=PANEL, references=None):
    rows, proof = attestation(root, frozen, image, manifest, panel, references)
    attested = len(rows)
    comparators = {}
    for tool in RIVALS:
        matched = [(row, row["original_rivals"][tool]) for row in rows
                   if row["original_rivals"][tool]["status"] == "success"]
        score_deltas = [row["candidate_score"] - old["score"] for row, old in matched]
        runtime_deltas = [old["runtime_seconds"] - row["candidate_runtime_seconds"]
                          for row, old in matched]
        comparators[tool] = {
            "paired": len(matched),
            "unpaired_among_finished": attested - len(matched),
            "unfinished_cases": EXPECTED_CASES - attested,
            "missing_or_failed_total": EXPECTED_CASES - len(matched),
            "score": signed_power(score_deltas),
            "runtime": signed_power(runtime_deltas),
        }
    complete, full_cohort, status = cohort_status(attested, comparators)
    return {
        "schema": SCHEMA,
        "scope": "COMPLETE_COHORT_DIAGNOSTIC" if complete else "EXPLICITLY_PARTIAL",
        "attested_finished_cases": attested,
        "expected_cases": EXPECTED_CASES,
        "attestation": proof,
        "candidate_alignment_recomputed": references is not None,
        "pinned": {"image_sha256": image, "manifest_sha256": manifest, "panel_sha256": panel},
        "comparators": comparators,
        "full_cohort_eligible": full_cohort,
        "status": status,
        "qualification_claim": "NONE",
    }


def self_test():
    """Synthetic boundary, tie, missing-arm, zero and minimum checks."""
    assert signed_power([1, -1])["verdict"] == "fails_nonpositive_at_r_zero"
    assert signed_power([1, 0, -1])["verdict"] == "fails_nonpositive_at_r_zero"
    assert signed_power([1, 0, 0])["verdict"] == "dominates_on_observed_pairs"
    assert signed_power([0, 0])["tail"]["all_zero_deltas"] is True
    assert signed_power([0, 0])["verdict"] == "fails_nonpositive_at_r_zero"
    assert signed_power([2, 2, -3])["verdict"] == "fails_negative_high_r_tail"
    assert signed_power([-1, 100])["verdict"] == "fails_nonpositive_at_r_zero"
    assert signed_power([-1, 100, 100])["verdict"] == "dominates_on_observed_pairs"
    assert signed_power([])["verdict"] == "no_paired_successes"
    assert tail_profile([2, 2, -3])["top_net_count"] == -1
    assert tail_profile([1, 1, 1])["min_tail_count"] == 3
    all_paired = {tool: {"paired": EXPECTED_CASES} for tool in RIVALS}
    missing_arm = dict(all_paired, abyss={"paired": EXPECTED_CASES - 1})
    assert cohort_status(EXPECTED_CASES, all_paired)[1] is True
    assert cohort_status(EXPECTED_CASES, missing_arm)[1] is False
    assert cohort_status(EXPECTED_CASES - 1, all_paired) == (
        False, False, "PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="read-only audited case root")
    parser.add_argument("--frozen-root", type=Path, help="read-only frozen seven root")
    parser.add_argument("--out", type=Path, help="optional new output file (never inside the audited root)")
    parser.add_argument("--projects-json", type=Path, help="pinned MiCall reference catalog for score readback")
    parser.add_argument("--hxb2-fasta", type=Path, help="pinned HXB2 FASTA for score readback")
    parser.add_argument("--self-test", action="store_true", help="run synthetic logic checks only")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("SELF_TEST_OK")
        return 0
    if not args.root or not args.frozen_root:
        parser.error("--root and --frozen-root are required unless --self-test is used")
    if bool(args.projects_json) != bool(args.hxb2_fasta):
        parser.error("--projects-json and --hxb2-fasta must be supplied together")
    references = (load_scoring_panel(args.projects_json, args.hxb2_fasta, PANEL)
                  if args.projects_json else None)
    report = diagnose(args.root, args.frozen_root, references=references)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        resolved = args.out.resolve()
        if any(resolved.is_relative_to(root.resolve()) for root in (args.root, args.frozen_root)):
            parser.error("--out must be outside both audited roots")
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")
    print("AUDIT_SCOPE", report["status"], "attested", report["attested_finished_cases"],
          "of", report["expected_cases"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
