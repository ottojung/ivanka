"""Attest and export synthetic MiCall-only diagnostic numbers for all tools."""
import json
import math
from pathlib import Path

from .sam_metrics import public_diagnostics

SCHEMA = "assembler-bench.public-mapping-diagnostics.v1"
CATALOG = {
    "soft_clipped_reads": ("Soft-clipped primary reads", "reads"),
    "soft_clip_events": ("Soft-clip events", "events"),
    "soft_clipped_bases": ("Soft-clipped bases", "nt"),
    "clipped_read_fraction": ("Fraction of mapped reads clipped", "fraction"),
    "soft_clipped_bases_per_1000_read_bases": (
        "Clipped bases per 1,000 mapped read bases", "nt / 1000 nt"),
    "soft_clip_events_per_1000_primary_mapped": (
        "Clip events per 1,000 mapped reads", "events / 1000 reads"),
    "primary_mapped": ("Primary mapped reads", "reads"),
    "primary_unmapped": ("Primary unmapped reads", "reads"),
    "primary_mapped_fraction": ("Primary mapped read fraction", "fraction"),
    "secondary": ("Secondary alignments", "records"),
    "supplementary": ("Supplementary alignments", "records"),
    "mean_known_mapq": ("Mean known MAPQ", "phred score"),
    "mapq_zero": ("Primary reads with MAPQ 0", "reads"),
    "aligned_read_bases": ("Aligned primary-read bases", "nt"),
    "inserted_bases": ("Mapped primary-read insertion bases", "nt"),
    "deleted_reference_bases": ("Mapped reference deletion bases", "nt"),
    "nuc_soft_clips_count": ("MiCall per-position clip aggregate", "count"),
    "nuc_q15_mean_depth": ("Mean Q15 depth", "reads / site"),
    "nuc_q15_covered_fraction": ("Q15 breadth", "fraction"),
    "region_concordance_mean": ("Mean region concordance", "percentage"),
    "final_contig_count": ("Final contig count", "contigs"),
    "final_contig_total_bases": ("Total contig bases", "nt"),
    "final_contig_31mer_redundancy_fraction": (
        "Redundant contig 31-mer fraction", "fraction"),
}


def checked_snapshot(source, public):
    """Compare a case with the already independently checked public preview."""
    source, public = Path(source), Path(public)
    rows = json.loads(public.read_text())["runs"]
    preview = next((r for r in rows if r.get("hxb2_truth_verified")), None)
    if preview is None or not preview.get("samples"):
        raise ValueError("missing HXB2 independently verified public preview")
    case = json.loads((source / "matrix.json").read_text())
    if (case.get("truth_validation", {}).get("valid") is not True
            or case["truth_validation"].get("cohort_sha256")
            != preview.get("cohort_manifest_sha256")
            or set(case["results"]) != set(preview["tools"])):
        raise ValueError("source case does not match verified cohort/tools")
    chosen = preview["samples"][0]
    for name in preview["tools"]:
        origin = case["results"][name]
        if (origin.get("status") != "success"
                or origin.get("sha256") != preview["images"][name]
                or not math.isclose(origin.get("score", float("nan")),
                                    chosen["score"].get(name, float("nan")),
                                    abs_tol=1e-10)
                or not math.isclose(origin.get("seconds", float("nan")),
                                    chosen["seconds"].get(name, float("nan")),
                                    abs_tol=1e-7)):
            raise ValueError("source tool record differs from verified preview")
    metrics = {}
    for name in preview["tools"]:
        detail = public_diagnostics(source / name)
        sam = detail["mapping"]
        csv = detail["micall_csv"]
        values = dict(sam.get("values", {}))
        values["nuc_soft_clips_count"] = csv["values"]["soft_clips_count"]
        for field in ("nuc_q15_mean_depth", "nuc_q15_covered_fraction",
                      "region_concordance_mean", "final_contig_count",
                      "final_contig_total_bases",
                      "final_contig_31mer_redundancy_fraction"):
            values[field] = csv["values"].get(field)
        metrics[name] = {
            "status": sam["status"],
            "source_sha256": sam.get("source_sha256"),
            "mapping_stage": sam.get("mapping_stage"),
            "denominators": sam.get("denominators", {}),
            "values": {key: value for key, value in values.items()
                       if key in CATALOG},
            "unavailable": [key for key in CATALOG if
                            values.get(key) is None],
        }
    return {"schema": SCHEMA, "run_id": preview["id"],
            "sample_alias": chosen["alias"], "status": "INCOMPLETE",
            "cases_measured": 1, "expected_cases": preview["expected_sample_count"],
            "cohort": "HXB2-derived synthetic / MiCall",
            "note": ("One fully verified completed example only; not a "
                     "400-case cohort or seven-way qualification. Current "
                     "image fork-commit provenance is not yet verified."),
            "metric_catalog": {key: {"label": label, "unit": unit}
                               for key, (label, unit) in CATALOG.items()},
            "tools": metrics}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--public-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = checked_snapshot(args.source, args.public_json)
    with args.out.open("x") as dest:
        json.dump(report, dest, sort_keys=True, separators=(",", ":"))
        dest.write("\n")
    print("PUBLIC_METRICS_INCOMPLETE_PREVIEW", len(report["tools"]))


if __name__ == "__main__":
    main()
