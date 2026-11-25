"""Publication-boundary transform for the tool-neutral Assembler Bench site.

Private publishers compute Ivanka project acceptance from authenticated
receipts. This module converts their output into the public /bench/ data
contract: no external-acceptance vocabulary and a cohort-owned assembler
roster that merges every attested tool. All assemblers are equal here; there
is no baseline/additional class. Only null placeholders and receipt-bound
measurements are added, and PX scores are joined to canonical cases only when
the case hashes and score units are independently validated.
"""
import copy
import json
import re

from .current_inputs import PANEL, PHYSICAL_MANIFEST
from .current_validation_v2 import V6_COHORT_SHA
from .public_psi import public_matrix
from . import px_timing_semantics as timing
from .public_vocabulary import find_tokens
from .px_ram_semantics import (COMPARABLE_KEY, LAUNCHER_DIAGNOSTIC, METHOD_KEY,
                               RAW_BYTES_KEY, SCOPE_KEY, UNAVAILABLE_KEY,
                               VERSION_KEY)

EVIDENCE_SCHEMA = "ivanka.assembler-bench.assembler-evidence.v1"

# Acceptance metadata that expresses project policy, not a measurement.
DROP_KEYS = frozenset((
    "eligible_for_expanded", "expanded_status", "expanded_qualification",
    "qualification_effect", "cohort_eligible", "status_reason",
    "qualification_admission", "qualifying", "not_qualifying",
))

# Exact public strings that may carry acceptance vocabulary. Unknown strings
# with a forbidden token are rejected rather than silently rewritten.
REPLACE = {
    "ineligible": "archived",
    "passed-original-only": "complete",
    "receipted-nonqualifying-evidence": "verified-evidence",
    "EXTERNALLY_ATTESTED_NOT_BENCHMARK_QUALIFIED": "EXTERNALLY_ATTESTED",
    "ivanka.external-caps-qualification.v1": "ivanka.external-caps.v1",
    "Sampled RSS is not an exact kernel hard cap; no legacy success is "
    "silently requalified.":
        "Sampled RSS is not an exact kernel hard cap; original measurements "
        "keep their attested execution policy.",
}

SHA64 = re.compile(r"^[0-9a-f]{64}$")
TOOL_STATUS = frozenset(("measured", "pending", "failed", "unavailable"))
PHYSICAL_SCORE = "micall_final_max_reference_panel_v1"
SYNTHETIC_SCORE = "micall_final_max_abundant_truths_balanced_v2"


def scrub(value):
    """Recursively remove acceptance metadata while preserving evidence."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key)
            if name.lower() in DROP_KEYS or find_tokens(name):
                continue
            result[key] = scrub(item)
        return result
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        tokens = find_tokens(value)
        if not tokens:
            return value
        if value in REPLACE:
            return REPLACE[value]
        raise ValueError("unmapped external acceptance text: " + value[:160])
    return value


def assert_clean_object(obj):
    """Fail if any serialized field of a public document is not neutral."""
    tokens = find_tokens(json.dumps(obj, sort_keys=True))
    if tokens:
        raise ValueError("external acceptance token in public document: " +
                         ",".join(tokens))


def _canonical_alias(case):
    """Only a canonical one-based alias may be joined to a cohort sample."""
    alias = case.get("canonical_alias", "")
    if not isinstance(alias, str) or not re.fullmatch(r"[RH][0-9]{3}", alias):
        raise ValueError("per-case evidence lacks a canonical alias")
    return alias


def validate_case_evidence(case, cohort, score_origin):
    """Prove the paired input hash and comparable score unit of a case row."""
    manifest = {"real": PHYSICAL_MANIFEST,
                "synthetic": V6_COHORT_SHA}.get(cohort)
    mates = case.get("read_sha256") or case.get("input_sha256") or {}
    paired = (SHA64.fullmatch(case.get("paired_input_sha256", "")) or
              (set(mates) == {"R1", "R2"} and
               all(SHA64.fullmatch(mates.get(key, "")) for key in ("R1", "R2"))))
    if (not manifest or case.get("canonical_manifest_sha256") != manifest
            or not paired):
        raise ValueError("case evidence is not bound to the cohort manifest")
    reads = case.get("read_sha256") or case.get("input_sha256")
    if reads is not None:
        if (not isinstance(reads, dict) or set(reads) != {"R1", "R2"}
                or any(not SHA64.fullmatch(reads[key])
                       for key in ("R1", "R2"))):
            raise ValueError("case evidence lacks both paired read hashes")
    elif not case.get("paired_input_method"):
        raise ValueError("case evidence lacks paired-input validation")
    expected = {"real": PHYSICAL_SCORE, "synthetic": SYNTHETIC_SCORE}.get(cohort)
    if (score_origin != expected
            or case.get("score_origin") != expected):
        raise ValueError("case score unit differs from the cohort score unit")
    if cohort == "real" and case.get("reference_panel_sha256") != PANEL:
        raise ValueError("physical case uses a different reference panel")
    if type(case.get("binding_receipts")) is not int or case[
            "binding_receipts"] < 2:
        raise ValueError("case input hash is not independently corroborated")
    score = case.get("score")
    if case.get("outcome") == "failure":
        if score is not None or not case.get("failure_reason"):
            raise ValueError("failed case must not invent a score or omit its reason")
    elif type(score) not in (int, float) or score < 0:
        raise ValueError("case evidence has no genuine score")
    if case.get(timing.RUNTIME_KEY) is not None or timing.has_proof_keys(case):
        if not timing.attested(case):
            raise ValueError("case runtime lacks complete timing proof")
        runtime = timing.comparable_seconds(case)
        if runtime is None or case.get(timing.RUNTIME_KEY) != runtime:
            raise ValueError("case runtime differs from its timing proof")
    return _canonical_alias(case)


def _provenance(item):
    return {
        key: value for key, value in (
            ("source_commit", item.get("source_commit")),
            ("adapter_commit", item.get("adapter_commit")),
            ("image_sha256", item.get("image_sha256")),
            ("source_url", item.get("source_url")),
            ("source_branch", item.get("source_branch")),
        ) if value is not None
    }


def _status(run, tool_id, cases):
    """Status reflects actual observations, never placeholder roster rows."""
    samples = run.get("samples", [])
    observed = any(isinstance(s.get("score", {}).get(tool_id), (int, float))
                   for s in samples)
    # A case is genuine evidence only when it carries a measured score.
    attested = any(isinstance(case.get("score"), (int, float))
                   for case in cases)
    if observed or attested:
        return "measured"
    if run.get("images", {}).get(tool_id):
        return "pending"
    failures = sum(tool_id in s.get("failures", []) for s in samples)
    return "failed" if failures else "unavailable"


def cohort_tools(evidence, cohort, seen=None):
    """Resolve a cohort's explicitly declared roster (unions only if declared)."""
    declarations = evidence.get("cohorts", {})
    if cohort not in declarations:
        raise ValueError("cohort does not declare its own assembler roster")
    entry = declarations[cohort]
    if not isinstance(entry, dict):
        raise TypeError("cohort assembler declaration must be an object")
    if "union_of" in entry:
        seen = set(seen or ())
        if cohort in seen:
            raise ValueError("cyclic cohort roster union")
        seen.add(cohort)
        tools = []
        for source in entry["union_of"]:
            for tool in cohort_tools(evidence, source, seen):
                if tool not in tools:
                    tools.append(tool)
        return tools
    tools = entry.get("assemblers", [])
    if (not isinstance(tools, list) or not tools
            or len(tools) != len(set(tools))):
        raise ValueError("invalid declared cohort roster")
    return list(tools)


def _case_target(case, cohort, run):
    """Map an attested case to the run's alias space, checking score units."""
    alias = case["canonical_alias"]
    origin = case.get("score_origin")
    if cohort == "combined":
        if alias.startswith("R"):
            if origin != PHYSICAL_SCORE:
                raise ValueError("combined physical score unit mismatch")
            return "R-" + alias
        if origin != SYNTHETIC_SCORE:
            raise ValueError("combined synthetic score unit mismatch")
        return "S-" + alias
    expected = PHYSICAL_SCORE if cohort == "real" else SYNTHETIC_SCORE
    if origin != expected:
        raise ValueError("case score unit differs from cohort")
    return alias


def _join_scores(run, assemblers, joined):
    """Join score-bearing rows only after hash and unit validation."""
    cohort = run.get("cohort")
    if cohort not in ("real", "synthetic", "combined"):
        return
    index = {s["alias"]: s for s in run.get("samples", [])}
    for item in assemblers:
        tool = item["id"]
        for case in item.get("cases", []):
            # Component cohorts own their cases; a combined run joins them
            # through its explicitly declared union of those cohorts.
            case_cohort = case.get("cohort")
            if cohort == "combined":
                if case_cohort not in ("real", "synthetic"):
                    continue
            elif case_cohort != cohort:
                continue
            validate_case_evidence(
                case, case_cohort,
                PHYSICAL_SCORE if case_cohort == "real" else SYNTHETIC_SCORE)
            alias = _case_target(case, cohort, run)
            sample = index.get(alias)
            if sample is None:
                continue
            # Re-running the publisher must refresh verified evidence fields
            # even when a genuine score is already present. The score itself
            # is only written when this case supplies the original reading.
            existing = sample.get("score", {}).get(tool)
            if case.get("outcome") == "failure":
                if existing is not None:
                    raise ValueError("failure would overwrite a genuine score")
            elif existing is None:
                sample.setdefault("score", {})[tool] = float(case["score"])
                joined.append((run["id"], tool, alias))
            runtime = timing.comparable_seconds(case)
            if runtime is not None:
                prior = sample.get("seconds", {}).get(tool)
                if prior is not None:
                    if prior != runtime:
                        raise ValueError("runtime measurement would overwrite "
                                         "an existing value")
                else:
                    sample.setdefault("seconds", {})[tool] = float(runtime)
            evidence_row = sample.setdefault("measurement_evidence", {}).setdefault(tool, {
                key: case[key] for key in (
                    "canonical_alias", "canonical_manifest_sha256",
                    "paired_input_sha256", "read_sha256", "score_origin",
                    "reference_panel_sha256") if key in case})
            if case.get("outcome") == "failure":
                if tool not in sample.setdefault("failures", []):
                    sample["failures"].append(tool)
                sample["score"][tool] = None
                sample["outcome"] = "failure"
            arm = sample.setdefault("diagnostics", {}).setdefault(tool, {})
            if isinstance(case.get("diagnostics"), dict) and case["diagnostics"]:
                arm.update(case["diagnostics"])
            # Withdraw any comparable peak published before the launcher-group
            # scope was known; only attested whole-container readings remain.
            if COMPARABLE_KEY in case:
                arm[COMPARABLE_KEY] = case[COMPARABLE_KEY]
            for key in (COMPARABLE_KEY, RAW_BYTES_KEY, METHOD_KEY, VERSION_KEY,
                        SCOPE_KEY, UNAVAILABLE_KEY, LAUNCHER_DIAGNOSTIC,
                        "input_sha256", "output_sha256", "exact_coverage",
                        "method", "scorer_source_sha256", "source_commit",
                        "adapter_commit", "image_sha256", "outcome",
                        "failure_reason", timing.RUNTIME_KEY,
                        timing.LAUNCHER_KEY, *timing.PROOF_KEYS):
                if key in case:
                    evidence_row[key] = case[key]


def merge_evidence(report, evidence):
    """Return a neutral report with cohort-owned rosters and validated joins."""
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported assembler evidence schema")
    result = scrub(copy.deepcopy(report))
    assemblers = scrub(evidence.get("assemblers", []))
    by_id = {item["id"]: item for item in assemblers}
    if len(by_id) != len(assemblers) or not assemblers:
        raise ValueError("duplicate or empty assembler evidence roster")
    joined = []
    for run in result.get("runs", []):
        # The run's pre-transform measurements define which tools already
        # have genuine observations. No privileged class is published.
        baseline = set(run.get("tools", []))
        tools = cohort_tools(evidence, run["cohort"])
        if not baseline <= set(tools):
            raise ValueError("declared roster lost a measured assembler")
        # Tools with attested per-case evidence are the only join candidates.
        # Re-running on an already transformed report preserves genuine scores
        # and can admit newly receipted measurements without fabrication.
        declared = {tool for tool in tools
                    if by_id.get(tool, {}).get("cases")}
        run["tools"] = tools
        for sample in run.get("samples", []):
            for key in ("score", "seconds"):
                row = sample.setdefault(key, {})
                for tool in tools:
                    row.setdefault(tool, None)
            diagnostics = sample.get("diagnostics")
            if isinstance(diagnostics, dict):
                for tool in tools:
                    diagnostics.setdefault(tool, {})
        _join_scores(run, [by_id[t] for t in declared if t in by_id], joined)
        for tool in tools:
            item = by_id.get(tool, {})
            cases = [case for case in item.get("cases", [])
                     if case.get("cohort") == run["cohort"]
                     or (run["cohort"] == "combined" and
                         case.get("cohort") in ("real", "synthetic"))]
            # Baseline observations live in the case rows, not in a synthetic
            # roster marker. Keep cases empty unless genuine attested rows exist.
            run.setdefault("_cases", {})[tool] = cases
        run["roster"] = [{
            "id": tool,
            "name": by_id.get(tool, {}).get("name", tool),
            "status": _status(run, tool, run["_cases"][tool]),
            "provenance": _provenance(by_id.get(tool, {})),
            "cases": run["_cases"][tool],
        } for tool in tools]
        run.pop("_cases", None)
        expected = run.get("expected_sample_count", run.get("sample_count", 0))
        # Progress is derived from the published case rows so newly joined
        # cohort receipts advance the per-tool counters without fabrication.
        run["tool_progress"] = {
            tool: {
                "expected": expected,
                "finished": sum(
                    sample.get("score", {}).get(tool) is not None
                    or tool in sample.get("failures", [])
                    for sample in run.get("samples", [])),
                "failed": sum(tool in sample.get("failures", [])
                              for sample in run.get("samples", [])),
            } for tool in tools}
        for image in list(run.get("images", {})):
            if image not in tools:
                run["images"].pop(image)
        for tool in tools:
            run.setdefault("images", {}).setdefault(tool, None)
        run["dominance_matrix"] = public_matrix(run)
    assert_clean_object(result)
    return result, joined


def sanitize_report(report):
    """Scrub a runs.json-style document without changing measurements."""
    result = scrub(copy.deepcopy(report))
    assert_clean_object(result)
    return result


def sanitize_document(document):
    """Scrub any other published JSON document (history, policy, attestation)."""
    return sanitize_report(document)
