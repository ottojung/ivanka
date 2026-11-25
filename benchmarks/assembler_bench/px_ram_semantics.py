"""Public RAM semantics for PX arms: comparable versus launcher-only samples.

The legacy PX launcher samples the launcher's process group. Containerized
MiCall processes run in a different process group, so those raw byte readings
are genuine observations but are *not* comparable whole-container peak RAM.
The public boundary therefore keeps the raw bytes and publishes their MiB
value only as an explicitly scoped launcher-group diagnostic. A comparable
peak is published only when the immutable, index-bound receipt attests the
sampling method, its version and whole-container scope. Post-hoc result and
resource side files cannot supply that attestation.
"""
import math

MIB = 1048576

COMPARABLE_METHOD = "container_process_tree_sampled_rss"
COMPARABLE_METHOD_VERSION = "ivanka.px.whole-container-rss.v2"
COMPARABLE_SCOPE = "whole_container_process_tree"
LEGACY_METHOD = "launcher_process_group_rss"
LEGACY_SCOPE = "launcher_process_group"

LAUNCHER_DIAGNOSTIC = "observed_launcher_group_peak_rss_mib"
METHOD_KEY = "peak_ram_method"
VERSION_KEY = "peak_ram_method_version"
SCOPE_KEY = "peak_ram_scope"
UNAVAILABLE_KEY = "peak_ram_unavailable_reason"
COMPARABLE_KEY = "peak_ram_observed_mib"
RAW_BYTES_KEY = "peak_rss_bytes"

UNAVAILABLE_REASON = (
    "Legacy launcher-process-group RSS excludes container MiCall processes; "
    "comparable whole-container peak is unavailable for this arm")


def sampler_fields(observation, *, method=LEGACY_METHOD, version=None,
                   scope=LEGACY_SCOPE):
    """Describe the sampler that actually produced a monitor observation.

    Callers must pass the real method and scope. A whole-container reading
    additionally needs an explicit version before it can be comparable.
    """
    if isinstance(observation, dict):
        peak = observation.get(RAW_BYTES_KEY, observation.get("peak_rss"))
        method = observation.get(METHOD_KEY, method)
        version = observation.get(VERSION_KEY, version)
        scope = observation.get(SCOPE_KEY, scope)
    else:
        peak = observation
    fields = {RAW_BYTES_KEY: peak, METHOD_KEY: method, SCOPE_KEY: scope}
    if version is not None:
        fields[VERSION_KEY] = version
    return fields


def observed_mib(value):
    """Convert an observed RSS byte count to MiB without inventing a sample."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return round(value / MIB, 6)


def attested(record):
    """Return whether a record explicitly attests comparable container scope."""
    if not isinstance(record, dict):
        return False
    return (record.get(METHOD_KEY) == COMPARABLE_METHOD
            and record.get(VERSION_KEY) == COMPARABLE_METHOD_VERSION
            and record.get(SCOPE_KEY) == COMPARABLE_SCOPE)


def classify(raw_bytes, receipt=None):
    """Return publication fields for one observed RSS reading.

    The raw byte reading is never changed. Only an explicit, versioned
    whole-container attestation on the immutable receipt promotes it to the
    comparable public metric; side files are post-hoc and never attest.
    """
    value = observed_mib(raw_bytes)
    diagnostics = {}
    fields = {RAW_BYTES_KEY: raw_bytes}
    if value is not None and attested(receipt):
        fields.update({COMPARABLE_KEY: value, METHOD_KEY: COMPARABLE_METHOD,
                       VERSION_KEY: COMPARABLE_METHOD_VERSION,
                       SCOPE_KEY: COMPARABLE_SCOPE})
        diagnostics.update({COMPARABLE_KEY: value, METHOD_KEY: COMPARABLE_METHOD,
                            VERSION_KEY: COMPARABLE_METHOD_VERSION,
                            SCOPE_KEY: COMPARABLE_SCOPE})
        return fields, diagnostics
    if value is None and attested(receipt):
        unavailable = {COMPARABLE_KEY: None, METHOD_KEY: COMPARABLE_METHOD,
                       VERSION_KEY: COMPARABLE_METHOD_VERSION,
                       SCOPE_KEY: COMPARABLE_SCOPE,
                       UNAVAILABLE_KEY: "No valid whole-container RSS observation"}
        fields.update(unavailable)
        return fields, dict(unavailable)
    fields.update({COMPARABLE_KEY: None, SCOPE_KEY: LEGACY_SCOPE,
                   UNAVAILABLE_KEY: UNAVAILABLE_REASON})
    diagnostics.update({COMPARABLE_KEY: None, SCOPE_KEY: LEGACY_SCOPE,
                        UNAVAILABLE_KEY: UNAVAILABLE_REASON})
    if value is not None:
        diagnostics[LAUNCHER_DIAGNOSTIC] = value
    return fields, diagnostics


def normalize_case(case, receipt=None):
    """Re-scope published evidence using only a bound receipt's attestation."""
    raw = case.get(RAW_BYTES_KEY)
    fields, diagnostics = classify(raw, receipt)
    previous = case.get("diagnostics") or {}
    merged = dict(previous)
    # A comparable reading from an unattested legacy receipt is withdrawn,
    # never silently retained under a different name.
    for key in (COMPARABLE_KEY, METHOD_KEY, VERSION_KEY):
        merged.pop(key, None)
    merged.update(diagnostics)
    case.update(fields)
    case["diagnostics"] = merged


def validate_publication(report, evidence):
    """Check every published tool row against its attested case evidence."""
    declared = {item["id"]: item for item in evidence.get("assemblers", [])}
    checked = 0
    for run in report.get("runs", []):
        tools = run.get("tools", [])
        if len(tools) != len(set(tools)):
            raise ValueError("duplicate public tool in run roster")
        samples = run.get("samples", [])
        for sample in samples:
            for tool, value in sample.get("score", {}).items():
                if tool not in declared:
                    continue
                alias = sample["alias"].split("-", 1)[-1]
                cases = [item for item in declared[tool].get("cases", [])
                         if item.get("canonical_alias") == alias]
                if not cases:
                    continue
                if value != cases[0].get("score") and value is not None:
                    raise ValueError("published score differs from case evidence")
                checked += 1
                arm = (sample.get("diagnostics") or {}).get(tool, {})
                proof = (sample.get("measurement_evidence") or {}).get(tool, {})
                case = cases[0]
                if case.get(COMPARABLE_KEY) is None:
                    if arm.get(COMPARABLE_KEY) is not None:
                        raise ValueError("unattested arm publishes comparable peak")
                    if proof.get(COMPARABLE_KEY) is not None:
                        raise ValueError("unattested proof publishes comparable peak")
                elif (arm.get(COMPARABLE_KEY) != case[COMPARABLE_KEY]
                      or proof.get(COMPARABLE_KEY) != case[COMPARABLE_KEY]):
                    raise ValueError("comparable peak disagrees with attested case")
                diag = case.get("diagnostics") or {}
                if LAUNCHER_DIAGNOSTIC in diag:
                    expected = observed_mib(case.get(RAW_BYTES_KEY))
                    if diag[LAUNCHER_DIAGNOSTIC] != expected:
                        raise ValueError("launcher diagnostic differs from raw bytes")
                if diag and arm != diag:
                    raise ValueError("published diagnostics differ from case evidence")
    return checked
