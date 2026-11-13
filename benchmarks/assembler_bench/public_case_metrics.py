"""Public numeric MiCall diagnostics from source-authenticated case records."""
import math

from .public_metrics import CATALOG


def numeric(values):
    return {
        key: value for key, value in values.items()
        if key in CATALOG and type(value) in (int, float)
        and math.isfinite(value) and value >= 0
    }


def synthetic(arm):
    details = arm.get("diagnostics") or {}
    sam = (details.get("mapping") or {}).get("values") or {}
    csv = (details.get("micall_csv") or {}).get("values") or {}
    values = dict(sam)
    values.update(csv)
    if "soft_clips_count" in csv:
        values["nuc_soft_clips_count"] = csv["soft_clips_count"]
    return numeric(values)


def physical(arm):
    values = (arm.get("metrics") or {}).get("diagnostics") or {}
    data = values.get("values") or {}
    result = dict(data)
    if "soft_clips_count" in data:
        result["nuc_soft_clips_count"] = data["soft_clips_count"]
    return numeric(result)


def validate_sample(sample, tools):
    """Reject fabricated or identifying per-case diagnostic evidence."""
    import re
    expected = set(tools)
    diagnostics = sample.get("diagnostics")
    profiles = sample.get("exact_profiles")
    if diagnostics is None and profiles is None:
        return
    if (not isinstance(diagnostics, dict)
            or set(diagnostics) != expected
            or not isinstance(profiles, dict)
            or set(profiles) - expected):
        raise ValueError("case metric tool identities do not match")
    for tool, values in diagnostics.items():
        if not isinstance(values, dict) or set(values) - set(CATALOG):
            raise ValueError("unknown per-case diagnostic measurement")
        for val in values.values():
            if (type(val) not in (float, int) or not math.isfinite(val)
                    or val < 0):
                raise ValueError("invalid per-case diagnostic number")
    for tool, profile in profiles.items():
        if (not isinstance(profile, dict)
                or any(not re.fullmatch("[a-f0-9]{64}",
                                    profile.get(key, "")) for key in (
                    "implementation_sha256", "selected_sequence_sha256",
                    "coverage_csv_sha256"))
                or type(profile.get("selected_length")) is not int
                or profile["selected_length"] < 1):
            raise ValueError("invalid exact-coverage provenance")
        from .exact_cache import SOURCE_SHA256
        if profile["implementation_sha256"] != SOURCE_SHA256:
            raise ValueError("unpinned exact-coverage implementation")
        for key in ("full_span", "inner_70"):
            series = profile.get(key)
            if (not isinstance(series, list) or not 1 <= len(series) <= 64
                    or any(type(x) not in (int, float)
                           or not math.isfinite(x) or x < 0
                           for x in series)):
                raise ValueError("invalid exact coverage positional profile")
