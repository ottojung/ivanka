"""Strict 198-sample score and runtime qualification; no inferred controls."""
import math

SAMPLE_COUNT = 198
MANIFEST_SHA256 = "4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192"
PANEL_SHA256 = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
IVA_IMAGE_SHA256 = "2af708df50c1023831cfbb3cfd11a2ae3694b51e0712071f0cb60b822088fbf3"
SCORE_FLOOR = 0.90
SAMPLE_CAP_SECONDS = 1800


def finite(value, *, positive=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else True)
    except OverflowError:
        return False


def psi(values):
    """Signed powers, with ties contributing 0 even when exponent is zero."""
    if len(values) != SAMPLE_COUNT or not all(finite(value) for value in values):
        raise ValueError("PSI requires 198 finite paired differences")
    gains = sum(value > 0 for value in values)
    losses = sum(value < 0 for value in values)
    try:
        linear = math.fsum(values) / SAMPLE_COUNT
        quadratic = math.fsum(value * abs(value) for value in values) / SAMPLE_COUNT
    except (OverflowError, ValueError) as exc:
        raise ValueError("Signed-power PSI moment overflow") from exc
    if not finite(linear) or not finite(quadratic):
        raise ValueError("Signed-power PSI moments must be finite")
    return {"psi0": (gains - losses) / SAMPLE_COUNT,
            "psi1": linear,
            "psi2": quadratic,
            "gains": gains, "losses": losses,
            "ties": SAMPLE_COUNT - gains - losses}


def qualify(records, names, iva_image, ivanka_image, sample_limit, panel_sha):
    """Return a report, never silently dropping invalid or unfinished samples."""
    selected = list(names)
    report = {"milestone198_pass": False, "milestone198_expected": SAMPLE_COUNT,
              "milestone198_valid_pairs": 0, "milestone198_errors": [],
              "milestone198_min_alignment_ratio": SCORE_FLOOR,
              "milestone198_time_measure": "MiCall command monotonic seconds measured inside each container",
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
            if record.get("status") != "finished" or record.get("failed") is not False:
                raise ValueError("Sample did not complete successfully")
            if record.get("iva_baseline_reused") is not True:
                raise ValueError("Missing verified IVA control")
            iva, ivanka = record["iva"], record["ivanka"]
            if (type(iva["exit_code"]) is not int or type(ivanka["exit_code"]) is not int
                    or iva["exit_code"] != 0 or ivanka["exit_code"] != 0):
                raise ValueError("One or both MiCall arms failed")
            if iva["image_id"] != iva_image or ivanka["image_id"] != ivanka_image:
                raise ValueError("Image provenance mismatch")
            if "metrics" not in iva or "metrics" not in ivanka:
                raise ValueError("Missing MiCall metrics")
            final = record["best_contig_acceptance"]
            if (final["method"] != "best_final_max_contig_local_alignment_over_reference_panel"
                    or final["reference_panel_sha256"] != PANEL_SHA256
                    or final["reference_count"] != 33):
                raise ValueError("Final MAX reference-panel evidence mismatch")
            pa, pk = final["iva_score"], final["ivanka_score"]
            if (iva.get("timing_origin") != "micall_in_container_monotonic_v1"
                    or ivanka.get("timing_origin") != "micall_in_container_monotonic_v1"):
                raise ValueError("Legacy or incompatible runtime measurement")
            ta, tk = iva["seconds"], ivanka["seconds"]
            # Post-container scoring and serialization are diagnostics, not
            # part of the frozen 1800s whole-container execution cap.
            elapsed = record["total_seconds"]
            iva_wall = iva["container_wall_seconds"]
            ivanka_wall = ivanka["container_wall_seconds"]
            if not all(finite(v, positive=True) for v in (pa, ta, tk)):
                raise ValueError("Missing or invalid IVA score or paired runtime")
            if not finite(pk) or pk < SCORE_FLOOR * pa:
                raise ValueError("Missing or insufficient Ivanka alignment score")
            if not finite(elapsed, positive=True):
                raise ValueError("Missing sample diagnostic elapsed time")
            if not all(finite(w, positive=True) and w <= sample_limit
                       for w in (iva_wall, ivanka_wall)):
                raise ValueError("Missing or excessive whole-container wall time")
            if ta > iva_wall + 1 or tk > ivanka_wall + 1:
                raise ValueError("In-container timer exceeds container lifetime")
            if final["pass"] is not True:
                raise ValueError("Per-sample alignment acceptance failed")
            score_deltas.append(pk - pa)
            time_deltas.append(ta - tk)
        except (AssertionError, KeyError, TypeError, ValueError):
            errors.append("incomplete_or_unqualified_pair:" + str(sample))
    report["milestone198_valid_pairs"] = len(score_deltas)
    if errors or len(score_deltas) != SAMPLE_COUNT:
        return report
    try:
        report["score_psi"] = psi(score_deltas)
        report["time_psi"] = psi(time_deltas)
    except ValueError:
        errors.append("nonfinite_or_overflowing_signed_power_psi")
        return report
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
