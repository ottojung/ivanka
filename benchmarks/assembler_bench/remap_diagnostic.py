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
import hashlib
import json
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


def _alias_cohort(alias):
    if isinstance(alias, str) and ALIAS.fullmatch(alias):
        return "real" if alias.startswith("R") else "synthetic"
    return None


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
        if _alias_cohort(alias) != rows["cohort"]:
            raise ValueError("remap case alias does not match row cohort")
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
            score = case.get("score")
            seconds = case.get("seconds")
            if not _number(score):
                raise ValueError("measured remap case lacks score or runtime")
            if (type(seconds) not in (int, float) or not math.isfinite(seconds)
                    or not 0 < seconds <= 2400):
                raise ValueError("measured remap seconds must be >0 and <=2400")
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


def _case_read_pairs(case):
    mates = case.get("read_sha256") or case.get("input_sha256") or {}
    if set(mates) == {"R1", "R2"} and all(_hash(mates[k]) for k in ("R1", "R2")):
        return {"R1": mates["R1"], "R2": mates["R2"]}
    return None


def _normalize_attested_inputs(attested_inputs, cohort):
    """Index independently attested input identities by canonical alias."""
    if attested_inputs is None:
        raise ValueError("remap merge requires independently attested input mapping")
    if isinstance(attested_inputs, dict) and "cases" in attested_inputs:
        records = attested_inputs["cases"]
    elif isinstance(attested_inputs, dict):
        records = [{"alias": k, **v} if isinstance(v, dict) else v
                   for k, v in attested_inputs.items()]
    elif isinstance(attested_inputs, list):
        records = attested_inputs
    else:
        raise ValueError("remap attested input mapping must be a dict or list")
    index = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("remap attested input record must be an object")
        alias = record.get("alias") or record.get("canonical_alias")
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            raise ValueError("remap attested input lacks a canonical alias")
        record_cohort = record.get("cohort", cohort)
        if record_cohort != cohort:
            continue
        if alias in index:
            raise ValueError("duplicate attested remap input alias")
        reads = record.get("read_sha256") or record.get("input_sha256")
        if not isinstance(reads, dict) or set(reads) != {"R1", "R2"}:
            raise ValueError("remap attested input lacks paired read hashes")
        if any(not _hash(reads[k]) for k in ("R1", "R2")):
            raise ValueError("remap attested input read hash invalid")
        manifest = record.get("canonical_manifest_sha256")
        if not _hash(manifest):
            raise ValueError("remap attested input manifest hash invalid")
        paired = record.get("paired_input_sha256")
        if paired is not None and not _hash(paired):
            raise ValueError("remap attested paired input hash invalid")
        index[alias] = {
            "alias": alias,
            "cohort": record_cohort,
            "canonical_manifest_sha256": manifest,
            "read_sha256": {"R1": reads["R1"], "R2": reads["R2"]},
            "paired_input_sha256": paired,
        }
    return index


def _assert_case_binding(case, rows, registry, attested):
    alias = case["alias"]
    cohort = rows["cohort"]
    if _alias_cohort(alias) != cohort:
        raise ValueError("remap case alias does not match row cohort")
    expected_panel = registry["reference_panel_sha256"]
    expected_manifest = registry["inputs"][cohort]
    if case["canonical_manifest_sha256"] != expected_manifest:
        raise ValueError("remap case uses a different cohort manifest")
    if case["reference_panel_sha256"] != expected_panel:
        raise ValueError("remap case uses a different reference panel")
    ref = attested.get(alias)
    if ref is None:
        raise ValueError("remap case is not in attested input mapping")
    if ref["canonical_manifest_sha256"] != case["canonical_manifest_sha256"]:
        raise ValueError("remap case manifest disagrees with attested input")
    reads = _case_read_pairs(case)
    if reads is None or reads != ref["read_sha256"]:
        raise ValueError("remap case read pair disagrees with attested input")
    paired = case.get("paired_input_sha256")
    if (_hash(paired) and _hash(ref.get("paired_input_sha256"))
            and paired != ref["paired_input_sha256"]):
        raise ValueError("remap case paired hash disagrees with attested input")
    return ref


def _tool_note(rows):
    cohort = rows.get("cohort")
    if cohort == "synthetic":
        scoring = ("synthetic hidden-truth post-hoc scoring; truth is never "
                   "mounted into reconstruction")
    else:
        scoring = ("physical scoring against the ordinary frozen reference "
                   "panel")
    return (f"Reference-based method; {scoring}; shared attested frozen image, "
            f"distinct run identity {rows['run_id']}")


def _merge_tool_note(existing, rows):
    note = _tool_note(rows)
    if not existing:
        return note
    if note in existing:
        return existing
    return existing + " " + note


def _rows_digest(rows):
    """Canonical digest of a validated delivery, stable across file readback.

    A run identity is a claim that one exact set of observations was
    published. Comparing this digest on re-merge catches every conflicting
    re-delivery (status, values, diagnostics, availability and provenance)
    without trusting any single displayed field.
    """
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def merge_diagnostic_report(report, registry, rows, attested_inputs=None):
    """Return an augmented copy of a public report for diagnostic display.

    Callers must opt in through the registry. ``attested_inputs`` must be an
    independently attested alias->read-pair/manifest mapping; rows are joined
    only when they match that mapping exactly. The frozen input document, its
    PSI certificate and every private gate input remain untouched.
    """
    validate_registry(registry)
    if not registry["enabled"]:
        return copy.deepcopy(report), 0
    validate_rows(rows)
    digest = _rows_digest(rows)
    if (rows["image_sha256"] != registry["image"]["sha256"]
            or rows["frozen_master_commit"] != registry["frozen_master_commit"]):
        raise ValueError("remap rows disagree with the registered frozen base")
    attested = _normalize_attested_inputs(attested_inputs, rows["cohort"])
    result = copy.deepcopy(report)
    if result.get("schema") != "ivanka.assembler-bench.public.v1":
        raise ValueError("unsupported public report schema")
    # A run identity belongs to one cohort across the whole report, not just
    # within a single run's methods list. Without this report-wide binding a
    # combined run could publish a second cohort under the first one's label.
    cohort_by_run = {}
    for published_run in result.get("runs", []):
        for method in published_run.get("diagnostic_methods", []):
            if method.get("id") != TOOL_ID:
                continue
            published_run_id = method.get("run_id")
            published_cohort = method.get("cohort")
            if published_cohort not in COHORTS or not isinstance(
                    published_run_id, str):
                raise ValueError("published remap method lacks a run/cohort binding")
            if (published_run_id in cohort_by_run
                    and cohort_by_run[published_run_id] != published_cohort):
                raise ValueError("remap run identity is bound to another cohort")
            cohort_by_run[published_run_id] = published_cohort
    if (rows["run_id"] in cohort_by_run
            and cohort_by_run[rows["run_id"]] != rows["cohort"]):
        raise ValueError("remap run identity is bound to another cohort")
    original_psi = copy.deepcopy(result.get("psi", {}))
    cases_by_cohort = {"real": [], "synthetic": []}
    for case in rows["cases"]:
        cases_by_cohort[rows["cohort"]].append(case)
    joined = 0
    for run in result.get("runs", []):
        cohorts = (("real", "synthetic") if run.get("cohort") == "combined"
                   else (run.get("cohort"),))
        applicable = [case for cohort in cohorts
                      for case in cases_by_cohort.get(cohort, [])]
        if not applicable:
            continue
        methods = run.setdefault("diagnostic_methods", [])
        same_run = [m for m in methods
                    if m.get("id") == TOOL_ID
                    and m.get("run_id") == rows["run_id"]]
        other_run_same_cohort = [
            m for m in methods
            if m.get("id") == TOOL_ID and m.get("cohort") == rows["cohort"]
            and m.get("run_id") != rows["run_id"]]
        if other_run_same_cohort:
            # One cohort cannot advertise two different remap run identities.
            raise ValueError("remap diagnostic method already present for cohort")
        if same_run:
            if any(m.get("cohort") != rows["cohort"] for m in same_run):
                raise ValueError("remap run identity is bound to another cohort")
            if any(m.get("rows_digest") != digest for m in same_run):
                # A status flip or any other content change under one run id
                # would leave two contradictory states in the same run.
                raise ValueError("conflicting remap rows reuse the same run identity")
            # Exact re-delivery: there is nothing new to publish.
            continue
        run.setdefault("tools", [])
        if TOOL_ID not in run["tools"]:
            run["tools"].append(TOOL_ID)
        roster = run.setdefault("roster", [])
        if not any(item.get("id") == TOOL_ID for item in roster):
            roster.append(_roster_entry(rows, registry))
        run.setdefault("tool_labels", {})[TOOL_ID] = LABEL
        mode_description = (
            "Ordinary frozen MiCall without --denovo; final MAX sequences "
            "scored by the cohort's ordinary post-hoc scorer. Physical "
            "reference-panel alignment may reflect the shared reference "
            "family and is diagnostic, not reference-blind assembly evidence."
        )
        run.setdefault("tool_modes", {})[TOOL_ID] = {
            "kind": METHOD_KIND, "de_novo": False,
            "description": mode_description}
        notes = run.setdefault("tool_notes", {})
        notes[TOOL_ID] = _merge_tool_note(notes.get(TOOL_ID), rows)
        run.setdefault("images", {})[TOOL_ID] = registry["image"]["sha256"]
        if not any(m.get("id") == TOOL_ID and m.get("run_id") == rows["run_id"]
                   for m in methods):
            methods.append({
                "id": TOOL_ID, "label": LABEL, "method": METHOD_KIND,
                "run_id": rows["run_id"],
                "cohort": rows["cohort"],
                "rows_digest": digest,
                "reference_panel_sha256": registry["reference_panel_sha256"],
            })
        index = {}
        for sample in run.get("samples", []):
            alias = sample.get("alias", "")
            if run.get("cohort") == "combined" and alias[:2] in ("R-", "S-"):
                alias = alias[2:]
            index[alias] = sample
        for case in applicable:
            _assert_case_binding(case, rows, registry, attested)
            sample = index.get(case["alias"])
            if sample is None:
                continue
            existing_score = sample.get("score", {}).get(TOOL_ID)
            existing_seconds = sample.get("seconds", {}).get(TOOL_ID)
            if existing_score is not None or existing_seconds is not None:
                # Idempotent only when identical.
                if (existing_score == case.get("score")
                        and existing_seconds == case.get("seconds")):
                    continue
                raise ValueError("duplicate remap case conflicts with published value")
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
            failures = sample.setdefault("failures", [])
            if case["status"] == "measured":
                # A published measurement and a published failure cannot
                # describe the same arm at once.
                if TOOL_ID in failures:
                    failures.remove(TOOL_ID)
                if sample.get("outcome") == "failure" and not failures:
                    sample["outcome"] = "success"
            else:
                if TOOL_ID not in failures:
                    failures.append(TOOL_ID)
                sample["outcome"] = "failure"
            joined += 1
        expected = run.get("expected_sample_count", run.get("sample_count", 0))
        finished = sum(1 for s in run.get("samples", [])
                       if isinstance((s.get("score") or {}).get(TOOL_ID),
                                     (int, float))
                       or TOOL_ID in (s.get("failures") or []))
        failed = sum(1 for s in run.get("samples", [])
                     if TOOL_ID in (s.get("failures") or []))
        run.setdefault("tool_progress", {})[TOOL_ID] = {
            "expected": expected, "finished": finished, "failed": failed,
        }
        run["dominance_matrix"] = public_matrix(run)
    if result.get("psi", {}) != original_psi:
        raise ValueError("diagnostic merge changed a published PSI certificate")
    assert_clean_object(result)
    return result, joined
