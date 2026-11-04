"""Fail-closed display of an existing strict 198-sample runner summary.

Only inspects the runner-written summary. It is NOT independent verification
of FASTQ checksums or physical container execution. The original runner owns
those checks; never use this summary as a substitute for preserved artifacts.
"""
import math
import re

from milestone198 import (IVA_IMAGE_SHA256, MANIFEST_SHA256, PANEL_SHA256,
                          SAMPLE_CAP_SECONDS, SAMPLE_COUNT, SCORE_FLOOR)

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def evaluate(summary):
    reasons = []
    if not isinstance(summary, dict):
        return {"invocation": None, "pass": False, "reasons": ["invalid summary object"]}
    invocation = summary.get("invocation")
    if not isinstance(invocation, str) or not invocation:
        reasons.append("missing invocation ID")
    for key in ("qualification_requested", "qualification198_requested", "all_projects"):
        if summary.get(key) is not True:
            reasons.append(key + " is not true")
    for key in ("allow_missing_baseline", "parallel_arms",
                "resumed_diagnostic_only", "stopped_early_after_irreversible_failure"):
        if summary.get(key) is not False:
            reasons.append(key + " is not false")
    if summary.get("mode") != "ivanka":
        reasons.append("expected Ivanka-only execution with cached original IVA")
    if summary.get("resumed_completed_samples") != 0:
        reasons.append("resumed/reused samples are not one physical invocation")
    for key in ("manifest_sample_count", "selected_samples", "finished_samples",
                "accepted_samples", "milestone198_valid_pairs", "milestone198_expected"):
        if type(summary.get(key)) is not int or summary[key] != SAMPLE_COUNT:
            reasons.append(key + " is not exactly 198")
    if summary.get("failed_samples") != [] or summary.get("milestone198_errors") != []:
        reasons.append("failed samples or runner qualification errors")
    if summary.get("manifest_sha256") != MANIFEST_SHA256:
        reasons.append("frozen manifest hash mismatch")
    if summary.get("reference_panel_sha256") != PANEL_SHA256:
        reasons.append("frozen reference panel hash mismatch")
    if summary.get("reference_panel_count") != 33:
        reasons.append("frozen reference count mismatch")
    if summary.get("iva_baseline_image_id") != IVA_IMAGE_SHA256:
        reasons.append("original IVA image mismatch")
    images = summary.get("images")
    candidate = images.get("ivanka") if isinstance(images, dict) else None
    if not isinstance(candidate, str) or not _SHA.fullmatch(candidate):
        reasons.append("missing pinned candidate image digest")
    if summary.get("milestone198_min_alignment_ratio") != SCORE_FLOOR:
        reasons.append("modified per-sample noninferiority floor")
    for key in ("hxb2_sha256", "project_reference_catalog_sha256"):
        value = summary.get(key)
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            reasons.append("invalid " + key)
    limit, wall = summary.get("sample_limit_seconds"), summary.get("max_container_wall_seconds")
    if (not _positive_number(limit) or limit > SAMPLE_CAP_SECONDS
            or not _positive_number(wall) or wall > limit):
        reasons.append("missing or excessive whole-container wall time")
    for kind in ("score", "time"):
        psi = summary.get(kind + "_psi")
        if (not isinstance(psi, dict) or psi.get("positive_all_nonnegative") is not True
                or psi.get("zeros_nonnegative") != []
                or psi.get("psi_at_positive_infinity") != "+inf"
                or any(not _positive_number(psi.get("psi" + str(k))) for k in range(3))):
            reasons.append(kind + " shifted-power PSI is not certified positive for all r>=0")
    if summary.get("milestone198_pass") is not True:
        reasons.append("runner did not certify milestone198_pass")
    return {
        "invocation": invocation,
        "required_samples": SAMPLE_COUNT,
        "pass": not reasons,
        "accepted_samples": summary.get("accepted_samples"),
        "finished_samples": summary.get("finished_samples"),
        "max_sample_seconds": wall,
        "time_label": "max_container_wall_seconds",
        "full_alpha_pass": False,
        "milestone198_pass": not reasons,
        "reasons": reasons,
    }
