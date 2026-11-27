"""Cohort-scale publication boundary for the reference-based remap diagnostic.

Single-case execution belongs to the controller and its CLI. This module only
folds already-attested terminal receipts from a whole cohort (or a pilot
subset) into the public Assembler Bench report, and proves that the decision
inputs are byte-identical with and without the diagnostic arms. It never
launches MiCall, never mounts truth or a panel into an assembler, never edits
published data, and never changes a qualification gate or denominator.
"""

import copy
import hashlib
import json

from assembler_bench import remap_diagnostic as display
from assembler_bench import remap_pilot_controller as ctl
from assembler_bench import remap_runner as runner

COHORT_SCHEMA = "ivanka.remap-diagnostic.cohort-publication.v1"
COHORTS = ("real", "synthetic")


def _digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _decision_view(report):
    """Decision-bearing content of a report, ignoring empty label containers.

    Merging a diagnostic arm creates empty maps for tool labels and evidence;
    those maps carry no measurement or decision, so they are pruned before the
    with/without-remap comparison. Every non-empty field is compared exactly.
    """
    def prune(value):
        if isinstance(value, dict):
            result = {key: prune(item) for key, item in value.items()}
            return {key: item for key, item in result.items()
                    if item != {} and item != []}
        if isinstance(value, list):
            return [prune(item) for item in value]
        return value

    return prune(display.qualification_view(report))


def _cohort_summary(cohort, run_id, rows, joined):
    statuses = {}
    for case in rows["cases"]:
        statuses[case["status"]] = statuses.get(case["status"], 0) + 1
    return {
        "cohort": cohort,
        "run_id": run_id,
        "case_count": len(rows["cases"]),
        "status_counts": dict(sorted(statuses.items())),
        "rows_digest": _digest(rows),
        "joined_samples": joined,
    }


def build_cohort_publication(*, report, registry, deliveries):
    """Fold terminal remap deliveries into a public report, additively.

    ``deliveries`` maps each cohort name to ``{"run_id", "receipts", "plans"}``.
    Receipts must be terminal and digest-valid, and the alias->read-pair mapping
    must come from attested plans rather than from the diagnostic rows. A cohort
    is published under one run identity; redelivering the same rows is a no-op.
    The returned artifact is a private preparation: the caller still has to
    authorize any public write.
    """
    if not isinstance(deliveries, dict) or not deliveries:
        raise ValueError("no remap cohort deliveries supplied")
    if set(deliveries) - set(COHORTS) or any(
            not isinstance(deliveries[cohort], dict)
            for cohort in deliveries):
        raise ValueError("invalid remap cohort delivery")

    before_digest = _digest(_decision_view(report))
    psi_before = copy.deepcopy(report.get("psi", {}))

    merged = copy.deepcopy(report)
    summaries = []
    total = 0
    for cohort in COHORTS:
        if cohort not in deliveries:
            continue
        delivery = deliveries[cohort]
        run_id = delivery.get("run_id")
        rows = runner.build_rows(
            delivery.get("receipts", []), run_id=run_id, cohort=cohort)
        display.validate_rows(rows)
        mapping = ctl.attested_input_mapping(delivery.get("plans", []))
        ctl.require_independent_attested_mapping(mapping, rows)
        merged, joined = display.merge_diagnostic_report(
            merged, registry, rows, attested_inputs=mapping)
        summaries.append(_cohort_summary(cohort, run_id, rows, joined))
        total += len(rows["cases"])

    # The public report may gain diagnostic arms; nothing else may change.
    if _digest(_decision_view(merged)) != before_digest:
        raise ValueError("remap publication changed a decision input")
    if merged.get("psi", {}) != psi_before:
        raise ValueError("remap publication changed PSI")
    display.validate_display_contract(merged)

    return {
        "schema": COHORT_SCHEMA,
        "qualification_claim": "NONE",
        "diagnostic_only": True,
        "executed_here": False,
        "published_here": False,
        "method": runner.TOOL_ID,
        "method_kind": runner.METHOD_KIND,
        "reference_based": True,
        "de_novo": False,
        "report": merged,
        "qualification_view_digest": before_digest,
        "psi_unchanged": True,
        "invariance_proven": True,
        "case_count": total,
        "cohorts": summaries,
    }
