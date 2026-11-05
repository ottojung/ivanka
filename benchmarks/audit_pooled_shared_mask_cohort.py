"""Read-only Q15 per-base shared-mask evidence, never haplotype coverage.

Original strict paired MiCall remap qnames count once across each selected
shared locus. Distinct paired sequences are NOT independent DNA molecules.
The report deliberately never includes reconstructed nucleotide strings.
"""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from discover_shared_mask_targets import file_sha256, read_sources
from screen_shared_mask_cohort import screen
from shared_block_consensus_candidate import audit_remap
from discover_shared_mask_cohort import write_private


def per_block(result):
    positions = result["positions"]
    full = result["complete_block_observations"]
    return {
        "mask_length": len(positions),
        "every_site_meets_q15_original_pair_depth_threshold": result["eligible"],
        "minimum_shared_base_q15_pair_ids": min(
            p["shared_base_qnames"] for p in positions),
        "minimum_shared_base_distinct_pair_sequences": min(
            p["shared_base_distinct_pair_sequences"] for p in positions),
        "maximum_alternative_base_pair_ids_at_one_site": max(
            p["other_base_qnames"] for p in positions),
        "complete_shared_allele_original_pair_ids":
            full["shared_allele_complete_read_pair_ids"],
        "complete_alternative_allele_original_pair_ids":
            full["alternative_complete_read_pair_ids"],
        "complete_shared_allele_distinct_pair_sequences":
            full["distinct_pair_sequence_evidence"][
                "shared_allele_distinct_pair_sequences"],
        "per_site": [
            {"site_zero_based": p["site"],
             "q15_shared_base_original_pair_ids": p["shared_base_qnames"],
             "q15_shared_base_distinct_pair_sequences":
                p["shared_base_distinct_pair_sequences"],
             "q15_alternative_base_original_pair_ids": p["other_base_qnames"],
             "q15_conflicting_original_pair_ids": p["conflicting_qnames"],
             "q15_conflicting_pair_sequences": p["conflicting_pair_sequences"],
             "q15_site_eligible_for_pooled_100_read_diagnostic": p["eligible"]}
            for p in positions],
        "original_pair_ids_are_independent_physical_molecules": False,
        "direct_complete_local_allele_is_full_length_phase": False,
    }


def audit_cohort(discovery, cohort, *, depth=100):
    if type(depth) is not int or depth < 1:
        raise ValueError("Expected positive original-pair depth threshold")
    provenance = screen(discovery, cohort, min_phred=15, marker_radius=600)
    cohort = Path(cohort).resolve(strict=True)
    current_sample, current_data = None, None
    records = []
    for entry in provenance["records"]:
        sample = entry["sample"]
        source = cohort / sample / "ivanka"
        if sample != current_sample:
            rows, refs, hashes = read_sources(source)
            original = source / "scratch" / "remap.csv"
            if hashes != {k: entry["source_sha256"][k]
                          for k in hashes} or file_sha256(original) != (
                              entry["source_sha256"]["original_remap_sam_csv"]):
                raise ValueError(f"{sample}: remap sources changed")
            with original.open(newline="") as stream:
                sam = list(csv.DictReader(stream))
            current_sample = sample
            current_data = ({r["region"]: r["sequence"] for r in rows}, refs, sam)
        finals, refs, sam = current_data
        region = entry["region"]
        masked = SimpleNamespace(
            sequence=finals[region], start=entry["mask_start"],
            end=entry["mask_end"])
        selected = {name: refs[name] for name in entry["selected_reference_names"]}
        result = audit_remap(masked, selected, sam, minimum_quality=15,
                             required_depth=depth)
        if len(result["positions"]) != entry["mask_length"]:
            raise ValueError("Observed shared allele disagrees with mask")
        records.append({**entry, "per_base_q15_pooled_support": per_block(result)})
    if len(records) != provenance["candidate_count"]:
        raise ValueError("Lost selected candidate during pooled depth audit")
    return {
        "schema_version": "ivanka.pooled_mask_original_pair_q15_audit.v1",
        "discovery_ledger_sha256": file_sha256(discovery),
        "candidate_count": len(records),
        "q15_depth_threshold_original_pair_ids": depth,
        "candidates_meeting_all_pooled_depth_guards": sum(
            r["per_base_q15_pooled_support"][
                "every_site_meets_q15_original_pair_depth_threshold"] for r in records),
        "candidates_with_any_complete_shared_allele_pair": sum(
            r["per_base_q15_pooled_support"][
                "complete_shared_allele_original_pair_ids"] > 0 for r in records),
        "records": records,
        "raw_fastq_per_mate_provenance_authenticated": False,
        "long_range_haplotype_phase_inferred": False,
        "haplotype_specific_read_depth_assigned": False,
        "independent_physical_molecules_inferred": False,
        "modifies_micall_consensus": False,
        "affects_198_acceptance": False,
        "interpretation": (
            "Pooled Q15 local original-pair counts from selected remap hypotheses "
            "only. Complete block is not a full haplotype. A distinct read-pair "
            "sequence is not an independent DNA molecule. No masks changed."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_discovery_json", type=Path)
    parser.add_argument("frozen_cohort", type=Path)
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_cohort(args.original_discovery_json,
                              args.frozen_cohort, depth=args.depth)
        if args.output:
            write_private(report, args.output, args.frozen_cohort)
        else:
            print(json.dumps(report, sort_keys=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
