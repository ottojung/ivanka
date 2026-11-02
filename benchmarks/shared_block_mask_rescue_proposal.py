"""Pure, guarded proposal to repair a shared-local MiCall consensus mask.

This is NOT wired into MiCall: no file writes, per-haplotype coverage claims,
or score-based selection. A candidate requires >=100 direct complete-block
Q15 read-pair observations of the *same* allele, >=100 distinct paired-read
sequences, and the existing per-site/unique-flank conservative guards.
"""
from shared_block_consensus_candidate import audit_remap


def propose_rescue(masked, references, sam_rows, minimum_quality=15,
                   required_depth=100):
    sequence, start, end = masked.sequence, masked.start, masked.end
    if (not isinstance(sequence, str) or not isinstance(start, int)
            or not isinstance(end, int) or start < 0 or end <= start
            or end > len(sequence) or sequence[start:end] != "x" * (end-start)):
        raise ValueError("Expected an exact nonempty lowercase-x mask interval")
    if minimum_quality < 0 or required_depth < 1:
        raise ValueError("Invalid quality or depth")
    audit = audit_remap(masked, references, sam_rows, minimum_quality,
                        required_depth)
    candidate = audit["read_derived_candidate"]
    full = audit["complete_block_observations"]
    spectrum = full["observed_complete_local_sequences"]
    exact = next((r for r in spectrum if r["sequence"] == candidate), None)
    exact_qnames = exact["read_pair_ids"] if exact else 0
    exact_distinct = exact["distinct_pair_sequences"] if exact else 0
    alternatives = [r for r in spectrum if r["sequence"] != candidate]
    # Requiring full-block observations avoids constructing a mosaic from
    # unrelated per-position majorities. Do not claim haplotype-specific phase.
    eligible = bool(audit["eligible"] and audit["sequence_diversity_guard_applied"]
                    and candidate and len(candidate) == end-start
                    and exact_qnames >= required_depth
                    and exact_distinct is not None
                    and exact_distinct >= required_depth
                    and all(r["read_pair_ids"] < required_depth
                            for r in alternatives))
    return {
        "eligible": eligible,
        "proposed_region_sequence": (
            sequence[:start] + candidate + sequence[end:] if eligible else None),
        "mask_start": start, "mask_end": end,
        "observed_complete_allele_pair_ids": exact_qnames,
        "observed_complete_allele_distinct_pair_sequences": exact_distinct,
        "alternative_complete_alleles": alternatives,
        "site_eligibility": audit["eligible"],
        "interpretation": "Pure shared-local sequence proposal, not per-haplotype "
                          "depth, phase, independent molecules, or a MiCall call.",
    }
