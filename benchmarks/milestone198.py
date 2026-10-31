"""Strict 198-sample score and runtime qualification; no inferred controls."""
import math

SAMPLE_COUNT = 198
MANIFEST_SHA256 = "4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192"
PANEL_SHA256 = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
SCORE_FLOOR = 0.90
SAMPLE_CAP_SECONDS = 1800


def finite(value, *, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else True))


def psi(values):
    """Signed powers, with ties contributing 0 even when exponent is zero."""
    if len(values) != SAMPLE_COUNT or not all(finite(value) for value in values):
        raise ValueError("PSI requires 198 finite paired differences")
    gains = sum(value > 0 for value in values)
    losses = sum(value < 0 for value in values)
    return {"psi0": (gains - losses) / SAMPLE_COUNT,
            "psi1": math.fsum(values) / SAMPLE_COUNT,
            "psi2": math.fsum(value * abs(value) for value in values) / SAMPLE_COUNT,
            "gains": gains, "losses": losses,
            "ties": SAMPLE_COUNT - gains - losses}


def qualify(records, names, iva_image, ivanka_image, sample_limit, panel_sha):
    """Return a report, never silently dropping invalid or unfinished samples."""
    selected = list(names)
    report = {"milestone198_pass": False, "milestone198_expected": SAMPLE_COUNT,
              "milestone198_valid_pairs": 0, "milestone198_errors": [],
              "milestone198_min_alignment_ratio": SCORE_FLOOR,
              "milestone198_time_measure": "MiCall arm wall seconds, both measured by the same runner",
              "score_psi": None, "time_psi": None}
    errors = report["milestone198_errors"]
    if len(selected) != SAMPLE_COUNT or len(set(selected)) != SAMPLE_COUNT:
        errors.append("cohort_not_exactly_198_unique")
    if len(records) != SAMPLE_COUNT:
        errors.append("completed_result_count_not_198")
    if not finite(sample_limit, positive=True) or sample_limit > SAMPLE_CAP_SECONDS:
        errors.append("sample_time_limit_invalid")
    if panel_sha != PANEL_SHA256:
        errors.append("reference_panel_mismatch")
    if len({r.get("sample") for r in records}) != len(records):
        errors.append("duplicate_completed_samples")
    if {r.get("sample") for r in records} != set(selected):
        errors.append("sample_set_mismatch")
    score_deltas, time_deltas = [], []
    for record in records:
        sample = record.get("sample", "<unidentified>")
        try:
            assert record.get("status") == "finished" and record.get("failed") is False
            assert record.get("iva_baseline_reused") is True
            iva, ivanka = record["iva"], record["ivanka"]
            assert iva["exit_code"] == 0 and ivanka["exit_code"] == 0
            assert iva["image_id"] == iva_image and ivanka["image_id"] == ivanka_image
            assert "metrics" in iva and "metrics" in ivanka
            final = record["best_contig_acceptance"]
            assert final["method"] == "best_final_max_contig_local_alignment_over_reference_panel"
            assert final["reference_panel_sha256"] == PANEL_SHA256
            assert final["reference_count"] == 33
            pa, pk = final["iva_score"], final["ivanka_score"]
            ta, tk = iva["seconds"], ivanka["seconds"]
            elapsed = record["total_seconds"]
            assert all(finite(v, positive=True) for v in (pa, ta, tk))
            assert finite(pk) and pk >= SCORE_FLOOR * pa
            assert finite(elapsed) and 0 <= elapsed <= sample_limit
            assert final["pass"] is True
            score_deltas.append(pk - pa)
            time_deltas.append(ta - tk)
        except (AssertionError, KeyError, TypeError, ValueError):
            errors.append("incomplete_or_unqualified_pair:" + str(sample))
    report["milestone198_valid_pairs"] = len(score_deltas)
    if errors or len(score_deltas) != SAMPLE_COUNT:
        return report
    report["score_psi"] = psi(score_deltas)
    report["time_psi"] = psi(time_deltas)
    for prefix in ("score", "time"):
        report.update({f"{prefix}_{key}": report[f"{prefix}_psi"][key]
                       for key in ("psi0", "psi1", "psi2", "gains", "losses", "ties")})
    report["milestone198_pass"] = all(
        report[category][key] > 0
        for category in ("score_psi", "time_psi")
        for key in ("psi0", "psi1", "psi2"))
    if not report["milestone198_pass"]:
        errors.append("one_or_more_signed_power_psi_not_positive")
    return report
