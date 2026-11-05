"""Fail-closed cohort screen: observed Q15 shared-block-to-marker pairs.

This is an optional, read-only research diagnostic. It does not edit original
MiCall inputs, assign independent molecules or infer complete haplotype phase.
"""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from discover_shared_mask_cohort import inventory, write_private
from discover_shared_mask_targets import read_sources, file_sha256
from shared_unphased_evidence import build_shared_evidence


def screen(ledger, cohort, *, min_phred=15, marker_radius=600):
    """Reproduce original discovery ledger, then screen its selected masks."""
    if (type(min_phred) is not int or min_phred < 15
            or type(marker_radius) is not int or marker_radius < 1):
        raise ValueError("Require Q15 or higher and positive marker radius")
    cohort = Path(cohort).resolve(strict=True)
    discovered = json.loads(Path(ledger).read_text())
    if discovered.get("schema_version") != "ivanka.shared_mask_cohort_discovery.v1":
        raise ValueError("Expected original immutable discovery v1 ledger")
    rebuilt = inventory(cohort, anchor=discovered["flank_anchor"],
                        minimum_length=discovered["minimum_mask_length"],
                        region_contains=discovered["region_contains"],
                        expected_samples=discovered["sample_count"])
    if discovered != rebuilt:
        raise ValueError("Original discovery source or candidate ledger changed")
    records = []
    for sample in rebuilt["samples"]:
        if not sample["target_candidates"]:
            continue
        source = cohort / sample["sample"] / "ivanka"
        rows, refs, _ = read_sources(source)
        final = {r["region"]: r["sequence"] for r in rows}
        remap = source / "scratch" / "remap.csv"
        if not remap.is_file():
            raise ValueError(f"{sample['sample']}: missing original remap rows")
        with remap.open(newline="") as stream:
            pairs = list(csv.DictReader(stream))
        remap_sha = file_sha256(remap)
        for case in sample["target_candidates"]:
            selected = {name: refs[name]
                        for name in case["selected_reference_names"]}
            masked = SimpleNamespace(
                sequence=final[case["region"]],
                start=case["mask_start"], end=case["mask_end"])
            result = build_shared_evidence(masked, selected, pairs,
                                           anchor=case["flank_anchor"],
                                           radius=marker_radius,
                                           minimum_quality=min_phred,
                                           include_direct_links=True)
            links = result["marker_direct_links"]
            records.append({
                "sample": sample["sample"],
                "region": case["region"],
                "mask_start": case["mask_start"],
                "mask_end": case["mask_end"],
                "mask_length": case["mask_length"],
                "selected_reference_names": case["selected_reference_names"],
                "source_sha256": {**sample["source_sha256"],
                                  "original_remap_sam_csv": remap_sha},
                "strict_original_pair_ids_evaluated":
                    result["strict_original_read_pair_ids_evaluated"],
                "marker_count": result["marker_count"],
                "per_marker_original_pair_links": [
                    value["direct_joint_observation_count"] for value in links],
                "per_marker_distinct_pair_sequence_signatures": [
                    value["direct_joint_distinct_pair_sequence_signatures"]
                    for value in links],
                "has_direct_link": any(
                    value["direct_joint_observation_count"] for value in links),
            })
    if len(records) != rebuilt["target_candidate_count"]:
        raise ValueError("A selected mask was not analyzed")
    return {
        "schema_version": "ivanka.shared_mask_direct_cohort_screen.v1",
        "source_discovery_ledger_sha256": file_sha256(ledger),
        "candidate_count": len(records),
        "candidates_with_direct_links": sum(r["has_direct_link"] for r in records),
        "candidates_without_eligible_markers": sum(
            r["marker_count"] == 0 for r in records),
        "candidates_with_markers_but_no_links": sum(
            r["marker_count"] > 0 and not r["has_direct_link"] for r in records),
        "minimum_phred": min_phred,
        "marker_radius": marker_radius,
        "records": records,
        "raw_fastq_provenance_authenticated": False,
        "long_range_haplotype_phase_inferred": False,
        "independent_physical_molecules_inferred": False,
        "haplotype_specific_depth_assigned": False,
        "modifies_micall_consensus": False,
        "affects_198_acceptance": False,
        "interpretation": ("Direct local linkage from original remap pair IDs "
                           "only. Distinct paired sequences are not independent "
                           "physical molecules. Markers do not establish full-"
                           "length phase or justify filling masked bases."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_discovery_json", type=Path)
    parser.add_argument("original_cohort_run", type=Path)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--marker-radius", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = screen(args.original_discovery_json, args.original_cohort_run,
                        min_phred=args.min_phred,
                        marker_radius=args.marker_radius)
        if args.output:
            write_private(result, args.output, args.original_cohort_run)
        else:
            print(json.dumps(result, sort_keys=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
