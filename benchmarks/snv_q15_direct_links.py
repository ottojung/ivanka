"""Original-Q15-pair-only local SNV links: never infer transitive edges."""
import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from snv_original_fastq_q15 import audit, private_output
from snv_q15_evidence import observe_pair
from snv_q15_fastq import iter_original_pairs
from snv_q15_sources import bound_candidates, verify_source

_STATES = ("reference", "alternative")
_PAIRS = tuple(a + "_" + b for a in _STATES for b in _STATES)
_ALTERNATIVE_PAIRS = tuple(e for e in _PAIRS
                           if e != "reference_reference")
_STATE_BITS = {"reference": 1, "alternative": 2, "missing": 4,
               "conflicting": 8}
_BIT_ALLELES = {1: "reference", 2: "alternative"}


def direct_links(audit_tsv, ordinary_fasta, original_r1, original_r2, *,
                 expected_hashes, min_phred=15, min_pairs=10,
                 max_pairs=50000):
    sources = {"audit_tsv": audit_tsv, "ordinary_fasta": ordinary_fasta,
               "original_r1": original_r1, "original_r2": original_r2}
    nodes = audit(audit_tsv, ordinary_fasta, original_r1, original_r2,
                  expected_hashes=expected_hashes, min_phred=min_phred,
                  min_pairs=min_pairs, max_pairs=max_pairs)
    candidates = bound_candidates(audit_tsv, ordinary_fasta)
    if len(candidates) != nodes["reported_local_snv_candidates"]:
        raise ValueError("Unstable local SNV source contract")
    pairs = list(combinations(range(len(candidates)), 2))
    counts = [Counter() for _ in pairs]
    # One global compact state-vector per original R1+R2 sequence signature,
    # rather than copying a 50k-pair dictionary for every candidate edge.
    signature_states = {}
    scanned = 0
    for _, r1, r2 in iter_original_pairs(original_r1, original_r2,
                                        max_pairs=max_pairs):
        scanned += 1
        calls = [observe_pair(item, r1, r2, min_phred)
                 for item in candidates]
        seq_signature = (r1[0], r2[0])
        vector = signature_states.setdefault(
            seq_signature, [0] * len(candidates))
        for i, state in enumerate(calls):
            vector[i] |= _STATE_BITS[state]
        for index, (a, b) in enumerate(pairs):
            event = calls[a] + "_" + calls[b]
            if event in _PAIRS:
                counts[index][event] += 1
    if scanned != nodes["pairs_scanned"]:
        raise ValueError("Original pair count changed during replay")
    for key, source in sources.items():
        verify_source(source, nodes["source_sha256"][key])
    unique_counts = [Counter() for _ in pairs]
    for vector in signature_states.values():
        for index, (a, b) in enumerate(pairs):
            if vector[a] in _BIT_ALLELES and vector[b] in _BIT_ALLELES:
                event = (_BIT_ALLELES[vector[a]] + "_" +
                         _BIT_ALLELES[vector[b]])
                unique_counts[index][event] += 1
    edges = []
    for index, (a, b) in enumerate(pairs):
        unique = unique_counts[index]
        # Reference/reference links merely show baseline co-coverage. They
        # cannot justify an edge involving a discovered alternative allele.
        supported = [
            event for event in _ALTERNATIVE_PAIRS
            if counts[index][event] >= min_pairs
            and unique[event] >= min_pairs]
        allowed = (nodes["candidates"][a]["candidate_meets_local_q15_screen"]
                   and nodes["candidates"][b]["candidate_meets_local_q15_screen"])
        edges.append({
            "candidate_indices_zero_based": [a, b],
            "observed_joint_original_pair_ids":
                {event: counts[index][event] for event in _PAIRS},
            "observed_joint_distinct_consistent_pair_sequences":
                {event: unique[event] for event in _PAIRS},
            "supported_direct_local_allele_combinations":
                supported if allowed else [],
            "direct_local_link_supported": allowed and bool(supported),
            "withheld_for_unqualified_node": not allowed,
            "joint_pair_counts_are_independent_physical_molecules": False,
            "haplotype_phase_inferred": False,
            "transitive_link_imputed": False,
        })
    return {
        "schema_version": "ivanka.snv_q15_direct_original_pair_links.v1",
        "source_sha256": nodes["source_sha256"],
        "original_pairs_scanned": scanned,
        "minimum_direct_original_pair_ids_and_signatures": min_pairs,
        "minimum_phred_all_31_bases": min_phred,
        "qualified_unphased_nodes": [
            {k: item[k] for k in ("parent_fasta_index",
                                  "snv_offset_zero_based",
                                  "baseline_base", "alternate_base",
                                  "candidate_meets_local_q15_screen")}
            for item in nodes["candidates"]],
        "candidate_pair_count": len(edges),
        "direct_allele_link_evidence": edges,
        "original_pair_ids_are_independent_physical_molecules": False,
        "full_length_haplotype_phase_inferred": False,
        "per_haplotype_coverage_assigned": False,
        "transitive_links_created": False,
        "modifies_micall_final_max": False,
        "changes_198_acceptance": False,
        "interpretation": ("Each directly reported local allele combination "
            "was observed in the SAME original R1/R2 pair at Q15 across "
            "two exact local 31-mers; repeated pair-sequence signatures "
            "require identical nonmissing joint observations. No "
            "transitive edges, distant phase or molecule independence."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    names = ("audit_tsv", "ordinary_fasta", "original_r1", "original_r2")
    for name in names:
        parser.add_argument(name, type=Path)
        parser.add_argument("--sha256-" + name.replace("_", "-"), required=True)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--min-pairs", type=int, default=10)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = [getattr(args, name) for name in names]
    hashes = {name: getattr(args, "sha256_" + name) for name in names}
    try:
        result = direct_links(*paths, expected_hashes=hashes,
                              min_phred=args.min_phred,
                              min_pairs=args.min_pairs,
                              max_pairs=args.max_pairs)
        if args.output:
            private_output(result, args.output, paths)
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
