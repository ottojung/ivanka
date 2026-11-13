"""Publish mapping evidence from completed, current-source MiCall cases."""
import math
import re

from .public_metrics import CATALOG, SCHEMA
from .metric_explanations import INFO


def catalog():
    return {
        key: {"label": label, "unit": unit, "description": INFO[key][0],
              "denominator": INFO[key][1], "stage": INFO[key][2],
              "suggested_direction": INFO[key][3]}
        for key, (label, unit) in CATALOG.items()}


def missing_arm():
    return {
        "status": "unmeasured", "source_sha256": None,
        "mapping_stage": None, "denominators": {},
        "values": {key: None for key in CATALOG},
        "unavailable": list(CATALOG)}


def measured_arm(row, sample, name, images):
    arm = row["results"][name]
    if (arm["status"] != "success"
            or arm["sha256"] != images[name]
            or not math.isclose(arm["score"], sample["score"][name],
                                rel_tol=0, abs_tol=1e-10)
            or not math.isclose(arm["seconds"], sample["seconds"][name],
                                rel_tol=0, abs_tol=1e-7)):
        raise ValueError("mapping metric source differs from completed run")
    data = arm.get("diagnostics") or {}
    mapping = data.get("mapping") or {}
    csv = data.get("micall_csv") or {}
    if (mapping.get("status") != "measured"
            or not re.fullmatch("[0-9a-f]{64}",
                                mapping.get("source_sha256") or "")):
        return None
    values = dict(mapping.get("values", {}))
    values["nuc_soft_clips_count"] = csv.get("values", {}).get(
        "soft_clips_count")
    for key in ("nuc_q15_mean_depth", "nuc_q15_covered_fraction",
                "region_concordance_mean", "final_contig_count",
                "final_contig_total_bases",
                "final_contig_31mer_redundancy_fraction"):
        values[key] = csv.get("values", {}).get(key)
    return {
        "status": mapping["status"],
        "source_sha256": mapping["source_sha256"],
        "mapping_stage": mapping["mapping_stage"],
        "denominators": mapping["denominators"],
        "values": {key: values.get(key) for key in CATALOG},
        "unavailable": [key for key in CATALOG if values.get(key) is None]}


def snapshot(rows, run):
    """Never substitute an obsolete case or invent a missing diagnostic."""
    ordered = sorted(rows, key=lambda row: row["id"])
    if len(ordered) != len(run["samples"]):
        raise ValueError("verified synthetic rows and public aliases diverged")
    selection = None
    for row, sample in zip(ordered, run["samples"]):
        if any(row["results"][name]["status"] != "success"
               for name in run["tools"]):
            continue
        arms = {name: measured_arm(row, sample, name, run["images"])
                for name in run["tools"]}
        if all(part is not None for part in arms.values()):
            selection = sample["alias"], arms
            break
    alias, tools = (selection if selection is not None
                    else (None, {name: missing_arm() for name in run["tools"]}))
    measured = int(selection is not None)
    return {
        "schema": SCHEMA, "run_id": run["id"],
        "sample_alias": alias, "status": "INCOMPLETE",
        "cases_measured": measured, "expected_cases": 400,
        "cohort": "Source-attested HXB2-derived synthetic MiCall",
        "note": ("One independently verified case's current mapping metrics."
                 if measured else
                 "No seven-arm complete mapping case yet; all diagnostics"
                 " remain unavailable, not zero."),
        "metric_catalog": catalog(), "tools": tools}
