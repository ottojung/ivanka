"""Publish current source-attested seven-way MiCall mapping diagnostics."""
import math

from .public_metrics import CATALOG, SCHEMA
from .metric_explanations import INFO


def snapshot(rows, run):
    """Copy only verified checkpoint diagnostic values, not private case paths."""
    expected = run["samples"][0]
    by_id = {row["id"]: row for row in rows}
    ordered = sorted(by_id)
    if not ordered:
        raise ValueError("no current synthetic cases for mapping diagnostics")
    row = by_id[ordered[0]]
    result = {}
    for tool in run["tools"]:
        arm = row["results"][tool]
        if (arm["status"] != "success"
                or arm["sha256"] != run["images"][tool]
                or not math.isclose(arm["score"], expected["score"][tool],
                                    rel_tol=0, abs_tol=1e-10)
                or not math.isclose(arm["seconds"], expected["seconds"][tool],
                                    rel_tol=0, abs_tol=1e-7)):
            raise ValueError("mapping diagnostic case/tool differs from preview")
        data = arm["diagnostics"]
        mapping, csv = data["mapping"], data["micall_csv"]
        values = dict(mapping["values"])
        values["nuc_soft_clips_count"] = csv["values"].get("soft_clips_count")
        for key in ("nuc_q15_mean_depth", "nuc_q15_covered_fraction",
                    "region_concordance_mean", "final_contig_count",
                    "final_contig_total_bases",
                    "final_contig_31mer_redundancy_fraction"):
            values[key] = csv["values"].get(key)
        result[tool] = {
            "status": mapping["status"],
            "source_sha256": mapping["source_sha256"],
            "mapping_stage": mapping["mapping_stage"],
            "denominators": mapping["denominators"],
            "values": {key: values.get(key) for key in CATALOG},
            "unavailable": [key for key in CATALOG if values.get(key) is None],
        }
    return {
        "schema": SCHEMA, "run_id": run["id"],
        "sample_alias": expected["alias"], "status": "INCOMPLETE",
        "cases_measured": 1, "expected_cases": 400,
        "cohort": "Source-attested HXB2-derived synthetic MiCall",
        "note": ("One verified case's metrics from the current pinned fork "
                 "image builds; no cohort-wide diagnostic certificate."),
        "metric_catalog": {
            key: {"label": label, "unit": unit, "description": INFO[key][0],
                  "denominator": INFO[key][1], "stage": INFO[key][2],
                  "suggested_direction": INFO[key][3]}
            for key, (label, unit) in CATALOG.items()},
        "tools": result,
    }
