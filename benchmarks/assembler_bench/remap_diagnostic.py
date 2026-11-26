"""Additive, opt-in registry for the reference-based MiCall remap method.

This module is a *publication boundary* only. It never runs MiCall, reads a
truth genome, changes a frozen report, or feeds a project acceptance gate.
The method is a diagnostic peer comparator: its scores, failures and absence
must be invisible to the private decision inputs, while the neutral /bench/
site may display it beside measured de novo methods when the caller opts in
with genuine rows from the separate runner.

Two invariants are enforced here:

* ``merge_diagnostic_report`` works on a deep copy and only adds rows that
  carry an authenticated receipt and explicit missingness. Unavailable
  metrics stay null; no zero, timing or contig is fabricated.
* ``qualification_view`` removes the method from every known private and
  public decision input. Tests apply the same decision to absent, present,
  failed and outlier remap rows and require an identical verdict.
"""
import copy
import math
import re

from .public_psi import public_matrix
from .public_view import assert_clean_object
from .px_ram_semantics import (
    COMPARABLE_KEY,
    METHOD_KEY,
    SCOPE_KEY,
    VERSION_KEY,
    attested,
)

REGISTRY_SCHEMA = "ivanka.assembler-bench.remap-registry.v1"
ROWS_SCHEMA = "ivanka.remap-diagnostic.rows.v1"

TOOL_ID = "micall-remap"
LABEL = "MiCall remap (reference-based)"
METHOD_KIND = "reference-based"
NOT_APPLICABLE = "not applicable"

# Mirrors the frozen original comparator roster used by the private physical
# decision. It is duplicated deliberately: importing a private gate here
# would couple the publication boundary to acceptance logic. The isolation
# test asserts that these constants stay equal to the gate's own roster.
QUALIFICATION_RIVALS = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet")

HASH64 = re.compile(r"^[0-9a-f]{64}$")
HASH40 = re.compile(r"^[0-9a-f]{40}$")
MASTER = re.compile(r"^[0-9a-f]{8,40}$")
RUN_ID = re.compile(r"^remap-[a-z0-9][a-z0-9_-]*$")
ALIAS = re.compile(r"^[RH][0-9]{3}$")
COHORTS = frozenset(("real", "synthetic"))
MEASURED_STATUSES = frozenset(("measured", "failed", "unavailable"))
# Outputs written only by the de novo / stitcher stages. Exact coverage and
# alignment are computed from the final MAX consensus in both modes and are
# therefore comparable; these are not.
DE_NOVO_ONLY = ("contig", "nuc_detail", "amino_detail", "conseq_region",
                "unstitched", "stitcher")


def de_novo_only(metric):
    """Whether a metric needs native or unstitched contigs."""
    name = str(metric).lower()
    return any(part in name for part in DE_NOVO_ONLY)

# Data that must never enter the reconstruction workflow through a row.
FORBIDDEN_INPUT_KEYS = frozenset(("truth", "truth_reference", "truth_fasta",
                                  "assembly_reference", "expected_genome"))
# Sampling-method annotations are strings, not measurements.
RAM_ANNOTATIONS = frozenset((METHOD_KEY, VERSION_KEY, SCOPE_KEY,
                             "unavailable_reason", "peak_ram_unavailable_reason"))


def _hash(value, pattern=HASH64):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _number(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and value >= 0)


def validate_registry(registry):
    """Fail closed on any registry that implies de novo assembly or a new gate."""
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("unsupported remap registry schema")
    if registry.get("tool_id") != TOOL_ID or registry.get("label") != LABEL:
        raise ValueError("remap tool identity drift")
    if registry.get("method_kind") != METHOD_KIND or registry.get("de_novo") is not False:
        raise ValueError("remap must be explicitly reference-based")
    invocation = registry.get("invocation")
    if (not isinstance(invocation, str) or "analyze sample" not in invocation
            or "--denovo" in invocation):
        raise ValueError("remap invocation is not the frozen non-de-novo mode")
    image = registry.get("image")
    if (not isinstance(image, dict) or not _hash(image.get("sha256"))
            or image.get("reuse") != "frozen-clinical-base"):
        raise ValueError("remap must reuse the attested frozen image honestly")
    if not _hash(registry.get("source_commit"), HASH40):
        raise ValueError("remap fork source pin missing")
    if not isinstance(registry.get("frozen_master_commit"), str) or not MASTER.fullmatch(
            registry["frozen_master_commit"]):
        raise ValueError("remap frozen clinical master pin missing")
    if not _hash(registry.get("reference_panel_sha256")):
        raise ValueError("remap reference panel pin missing")
    inputs = registry.get("inputs")
    if (not isinstance(inputs, dict) or not set(inputs) <= COHORTS
            or not inputs or any(not _hash(value) for value in inputs.values())):
        raise ValueError("remap input cohort manifest pins missing")
    guard = registry.get("guard")
    if (not isinstance(guard, dict)
            or guard.get("max_wall_seconds") != 2400
            or guard.get("max_rss_bytes") != 4_000_000_000
            or guard.get("cpu_allocation") != 2
            or guard.get("exclusive_execution_slot") is not True
            or guard.get("kernel_enforcement") is not False
            or not isinstance(guard.get("minimum_free_bytes"), int)
            or guard["minimum_free_bytes"] < 32 * 1024 ** 3):
        raise ValueError("remap does not declare the shared resource guard")
    if registry.get("acceptance_effect") != "none":
        raise ValueError("remap registry claims a project acceptance effect")
    if type(registry.get("enabled")) is not bool:
        raise ValueError("remap arm must be explicitly opt-in")
    return registry


def validate_rows(rows):
    """Validate one runner delivery: authentic inputs, honest missingness."""
    if not isinstance(rows, dict) or rows.get("schema") != ROWS_SCHEMA:
        raise ValueError("unsupported remap rows schema")
    if (rows.get("tool_id") != TOOL_ID
            or rows.get("method_kind") != METHOD_KIND
            or rows.get("mode") != METHOD_KIND
            or rows.get("denovo") is not False):
        raise ValueError("remap rows do not identify the reference-based method")
    if not RUN_ID.fullmatch(str(rows.get("run_id", ""))):
        raise ValueError("remap rows lack a distinct run identity")
    if not _hash(rows.get("image_sha256")):
        raise ValueError("remap rows lack the frozen image digest")
    if not isinstance(rows.get("frozen_master_commit"), str) or not MASTER.fullmatch(
            rows["frozen_master_commit"]):
        raise ValueError("remap rows lack the frozen master pin")
    if not _hash(rows.get("invocation_sha256")):
        raise ValueError("remap rows lack the exact invocation digest")
    if rows.get("cohort") not in COHORTS:
        raise ValueError("remap rows lack a canonical cohort")
    cases = rows.get("cases")
    if not isinstance(cases, list):
        raise ValueError("remap rows lack a case list")
    aliases = set()
    for case in cases:
        if not isinstance(case, dict) or FORBIDDEN_INPUT_KEYS & set(case):
            raise ValueError("truth genome reached a remap reconstruction row")
        alias = case.get("alias")
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            raise ValueError("remap case lacks a canonical cohort alias")
        if alias in aliases:
            raise ValueError("duplicate remap case alias")
        aliases.add(alias)
        if case.get("status") not in MEASURED_STATUSES:
            raise ValueError("remap case status must reflect an observation")
        if not _hash(case.get("reference_panel_sha256")):
            raise ValueError("remap case lacks reference-panel provenance")
        if not _hash(case.get("canonical_manifest_sha256")):
            raise ValueError("remap case lacks cohort manifest provenance")
        if not _hash(case.get("receipt_sha256")):
            raise ValueError("remap case lacks an immutable receipt digest")
        mates = case.get("read_sha256") or case.get("input_sha256") or {}
        paired = (_hash(case.get("paired_input_sha256", ""))
                  or (set(mates) == {"R1", "R2"}
                      and all(_hash(mates[key]) for key in ("R1", "R2"))))
        if not paired:
            raise ValueError("remap case is not bound to its original read pair")
        diagnostics = case.get("diagnostics", {})
        if not isinstance(diagnostics, dict):
            raise ValueError("remap diagnostics must be a metric mapping")
        unavailable = case.get("unavailable", [])
        if not isinstance(unavailable, list) or any(
                not isinstance(key, str) for key in unavailable):
            raise ValueError("remap unavailable metrics must be named")
        for key in unavailable:
            if diagnostics.get(key) is not None:
                raise ValueError("unavailable remap metric carries a value")
        for key, value in diagnostics.items():
            if key in RAM_ANNOTATIONS:
                if value is not None and not isinstance(value, str):
                    raise ValueError("remap sampling annotation must be text")
            elif value is not None and not _number(value):
                raise ValueError("remap metric is neither measured nor null")
        if (COMPARABLE_KEY in diagnostics
                and diagnostics[COMPARABLE_KEY] is not None
                and not attested(diagnostics)):
            raise ValueError("unattested launcher RSS promoted to comparable peak")
        for key in (METHOD_KEY, VERSION_KEY, SCOPE_KEY):
            if key in diagnostics and not isinstance(diagnostics[key], str):
                raise ValueError("remap RAM attestation fields must be strings")
        if case["status"] == "measured":
            if not _number(case.get("score")) or not _number(case.get("seconds")):
                raise ValueError("measured remap case lacks score or runtime")
        else:
            if case.get("score") is not None or case.get("seconds") is not None:
                raise ValueError("unmeasured remap case fabricates a measurement")
            if not case.get("failure_reason"):
                raise ValueError("unmeasured remap case lacks an explicit reason")
        # De novo-only outputs cannot be invented from a reference-based run.
        if case.get("unstitched_contigs") in (True, "present"):
            raise ValueError("reference-based remap cannot claim unstitched contigs")
        for key in set(diagnostics):
            if de_novo_only(key) and diagnostics[key] is not None:
                raise ValueError("de novo-only metric requires an explicit N/A")
        for key in unavailable:
            if de_novo_only(key) and key not in diagnostics:
                raise ValueError("de novo-only metric needs a null reading")
    return rows


def _strip_run(run):
    """Remove one diagnostic arm from a public run without re-scoring it."""
    if not isinstance(run, dict):
        return
    run["tools"] = [tool for tool in run.get("tools", []) if tool != TOOL_ID]
    run["roster"] = [item for item in run.get("roster", [])
                     if item.get("id") != TOOL_ID]
    for key in ("tool_progress", "images", "tool_labels", "tool_modes",
                "tool_notes"):
        if isinstance(run.get(key), dict):
            run[key].pop(TOOL_ID, None)
    run.pop("diagnostic_methods", None)
    if "dominance_matrix" in run:
        # Recompute rather than patch: a private consumer sees exactly the
        # matrix it would have seen before any diagnostic arm was merged.
        run["dominance_matrix"] = public_matrix(run)
    for sample in run.get("samples", []):
        for key in ("score", "seconds", "diagnostics", "measurement_evidence"):
            if isinstance(sample.get(key), dict):
                sample[key].pop(TOOL_ID, None)
        if TOOL_ID in sample.get("failures", []):
            sample["failures"].remove(TOOL_ID)
        if sample.get("outcome") == "failure" and not sample.get("failures"):
            sample["outcome"] = "success"


def validate_display_contract(report):
    """Check that published diagnostic metadata is honest and N/A is null."""
    checked = 0
    for run in report.get("runs", []):
        for method in run.get("diagnostic_methods", []):
            tool = method.get("id")
            if tool != TOOL_ID or tool not in run.get("tools", []):
                raise ValueError("undeclared diagnostic method in a run")
            if run.get("tool_labels", {}).get(tool) != LABEL:
                raise ValueError("diagnostic method label drift")
            mode = run.get("tool_modes", {}).get(tool, {})
            if (mode.get("kind") != METHOD_KIND
                    or mode.get("de_novo") is not False):
                raise ValueError("diagnostic method type is not explicit")
            for sample in run.get("samples", []):
                arm = sample.get("diagnostics", {}).get(tool, {})
                for key in arm.get("unavailable_reasons", {}):
                    if arm.get(key) is not None:
                        raise ValueError("unavailable diagnostic metric carries a value")
            checked += 1
    return checked


def qualification_view(artifact):
    """Strip every diagnostic arm from a decision input, returning a copy.

    Works for the private physical decision report, a public runs document,
    an assembler-evidence document and flat PSI delta lists. The private
    rosters are never widened by data arriving from the diagnostic runner.
    """
    if isinstance(artifact, list):
        return [copy.deepcopy(item) for item in artifact
                if not _is_diagnostic(item)]
    if not isinstance(artifact, dict):
        return artifact
    result = copy.deepcopy(artifact)
    if isinstance(result.get("comparators"), dict):
        result["comparators"] = {
            tool: row for tool, row in result["comparators"].items()
            if tool in QUALIFICATION_RIVALS}
    if "tools" in result:
        _strip_run(result)
    for run in result.get("runs", []):
        _strip_run(run)
    if isinstance(result.get("assemblers"), list):
        result["assemblers"] = [item for item in result["assemblers"]
                                if item.get("id") != TOOL_ID]
    for entry in result.get("cohorts", {}).values():
        if isinstance(entry, dict) and isinstance(entry.get("assemblers"), list):
            entry["assemblers"] = [tool for tool in entry["assemblers"]
                                   if tool != TOOL_ID]
    return result


def _is_diagnostic(item):
    return (isinstance(item, dict)
            and (item.get("tool") == TOOL_ID
                 or item.get("tool_id") == TOOL_ID
                 or item.get("method_kind") == METHOD_KIND))


def _roster_entry(rows, registry):
    cases = rows["cases"]
    observed = any(case["status"] == "measured" for case in cases)
    failed = any(case["status"] == "failed" for case in cases)
    status = "measured" if observed else "failed" if failed else "unavailable"
    return {
        "id": TOOL_ID,
        "name": LABEL,
        "status": status,
        "provenance": {
            "source_commit": registry["source_commit"],
            "image_sha256": registry["image"]["sha256"],
            "reference_panel_sha256": registry["reference_panel_sha256"],
            "shared_image_reuse": registry["image"]["reuse"],
            "frozen_master_commit": registry["frozen_master_commit"],
            "invocation_sha256": rows["invocation_sha256"],
        },
        # No de novo adapter and no attested PX case receipt: the scores live
        # in the read-only diagnostic rows, never in the attested evidence.
        "cases": [],
    }


def merge_diagnostic_report(report, registry, rows):
    """Return an augmented copy of a public report for diagnostic display.

    Callers must opt in through the registry. The frozen input document, its
    PSI certificate and every private gate input remain untouched.
    """
    validate_registry(registry)
    if not registry["enabled"]:
        return copy.deepcopy(report), 0
    validate_rows(rows)
    if (rows["image_sha256"] != registry["image"]["sha256"]
            or rows["frozen_master_commit"] != registry["frozen_master_commit"]):
        raise ValueError("remap rows disagree with the registered frozen base")
    result = copy.deepcopy(report)
    if result.get("schema") != "ivanka.assembler-bench.public.v1":
        raise ValueError("unsupported public report schema")
    original_psi = copy.deepcopy(result.get("psi", {}))
    cases_by_cohort = {"real": [], "synthetic": []}
    for case in rows["cases"]:
        if case["alias"].startswith("R"):
            cases_by_cohort["real"].append(case)
        else:
            cases_by_cohort["synthetic"].append(case)
    joined = 0
    for run in result.get("runs", []):
        cohorts = (("real", "synthetic") if run.get("cohort") == "combined"
                   else (run.get("cohort"),))
        applicable = [case for cohort in cohorts
                      for case in cases_by_cohort.get(cohort, [])]
        if not applicable:
            continue
        run.setdefault("tools", [])
        if TOOL_ID not in run["tools"]:
            run["tools"].append(TOOL_ID)
        run.setdefault("roster", []).append(_roster_entry(rows, registry))
        run.setdefault("tool_labels", {})[TOOL_ID] = LABEL
        run.setdefault("tool_modes", {})[TOOL_ID] = {
            "kind": METHOD_KIND, "de_novo": False,
            "description": ("Ordinary frozen MiCall without --denovo; final "
                            "MAX sequences scored against the ordinary "
                            "reference panel. A favorable alignment can "
                            "reflect the shared reference family and is a "
                            "diagnostic observation, not reference-blind "
                            "assembly performance.")}
        run.setdefault("tool_notes", {})[TOOL_ID] = (
            "Reference-based method; shared attested frozen image, distinct "
            "run identity " + rows["run_id"])
        run.setdefault("images", {})[TOOL_ID] = registry["image"]["sha256"]
        run.setdefault("diagnostic_methods", []).append({
            "id": TOOL_ID, "label": LABEL, "method": METHOD_KIND,
            "run_id": rows["run_id"],
            "reference_panel_sha256": registry["reference_panel_sha256"],
        })
        index = {}
        for sample in run.get("samples", []):
            alias = sample.get("alias", "")
            if run.get("cohort") == "combined" and alias[:2] in ("R-", "S-"):
                alias = alias[2:]
            index[alias] = sample
        for case in applicable:
            expected_panel = registry["reference_panel_sha256"]
            if (case["reference_panel_sha256"] != expected_panel
                    or case["canonical_manifest_sha256"]
                    != registry["inputs"][rows["cohort"]]):
                raise ValueError("remap case uses a different cohort or panel")
            sample = index.get(case["alias"])
            if sample is None:
                continue
            sample.setdefault("score", {})[TOOL_ID] = case.get("score")
            sample.setdefault("seconds", {})[TOOL_ID] = case.get("seconds")
            diagnostics = sample.setdefault("diagnostics", {}).setdefault(
                TOOL_ID, {})
            diagnostics.update(case.get("diagnostics", {}))
            for key in case.get("unavailable", []):
                diagnostics[key] = None
                diagnostics.setdefault("unavailable_reasons", {})[key] = (
                    NOT_APPLICABLE if de_novo_only(key)
                    else "not measured in this attempt")
            evidence = sample.setdefault("measurement_evidence", {}).setdefault(
                TOOL_ID, {})
            evidence.update({
                "receipt_sha256": case["receipt_sha256"],
                "reference_panel_sha256": case["reference_panel_sha256"],
                "image_sha256": rows["image_sha256"],
                "frozen_master_commit": rows["frozen_master_commit"],
                "invocation_sha256": rows["invocation_sha256"],
                "method": METHOD_KIND,
                "denovo": False,
            })
            for key in ("paired_input_sha256", "read_sha256",
                        "input_sha256"):
                if key in case:
                    evidence[key] = case[key]
            if case["status"] != "measured":
                failures = sample.setdefault("failures", [])
                if TOOL_ID not in failures:
                    failures.append(TOOL_ID)
                sample["outcome"] = "failure"
            joined += 1
        expected = run.get("expected_sample_count", run.get("sample_count", 0))
        run.setdefault("tool_progress", {})[TOOL_ID] = {
            "expected": expected,
            "finished": sum(case["status"] == "measured"
                            for case in applicable),
            "failed": sum(case["status"] == "failed" for case in applicable),
        }
        run["dominance_matrix"] = public_matrix(run)
    if result.get("psi", {}) != original_psi:
        raise ValueError("diagnostic merge changed a published PSI certificate")
    assert_clean_object(result)
    return result, joined
