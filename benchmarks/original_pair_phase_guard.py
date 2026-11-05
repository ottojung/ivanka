"""Reference-free read-pair phase conflict diagnostic for assembled contigs.

For each contig, discover locally observed single-base alternatives using
unique exact flanks and Q15 original paired reads. A recombinant is vetoed
only if directly co-observed opposite alleles contradict the contig and
zero original pairs directly support its own allele combination.
No transitive inference, missing-insert imputation or physical molecule claim.
"""
import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from original_pair_phase_calls import context_index, pair_q15_calls
from original_pair_phase_scope import scoped_indices
from snv_q15_fastq import iter_original_pairs
from snv_q15_sources import verify_source
from snv_original_fastq_q15 import private_output
from synthetic_phase_fidelity import fasta_records


def evaluate(sequence, mate_pairs, *, anchor=7, min_alleles=5,
             min_bridge_pairs=5, min_unique_signatures=3,
             exact_context_lookup=None, excluded_cross_contig_contexts=0):
    if not sequence or set(sequence) - set("ACGT"):
        raise ValueError("Only resolved A/C/G/T contigs are assessed")
    if (type(min_alleles) is not int or min_alleles < 1
            or type(min_bridge_pairs) is not int or min_bridge_pairs < 1
            or type(min_unique_signatures) is not int
            or min_unique_signatures < 1):
        raise ValueError("Positive integer original-pair thresholds required")
    if type(anchor) is not int or not 5 <= anchor <= 15:
        raise ValueError("Anchor must be an integer from 5 through 15 bases")
    index = (context_index(sequence, anchor=anchor)
             if exact_context_lookup is None else exact_context_lookup)
    records = []
    allele_counts = defaultdict(Counter)
    for signature, mate1, mate2 in mate_pairs:
        calls = pair_q15_calls(mate1, mate2, index, anchor=anchor)
        records.append((signature, calls))
        for pos, allele in calls.items():
            allele_counts[pos][allele] += 1
    variants = sorted(pos for pos, counts in allele_counts.items()
                      if counts[sequence[pos]] >= min_alleles
                      and any(counts[allele] >= min_alleles
                              for allele in "ACGT" if allele != sequence[pos]))
    edges = []
    contradictions = []
    for a, b in combinations(variants, 2):
        pairs = Counter()
        groups = defaultdict(set)
        for signature, calls in records:
            event = (calls.get(a), calls.get(b))
            groups[signature].add(event)
            if None not in event:
                pairs[event] += 1
        unique = Counter(next(iter(events)) for events in groups.values()
                         if len(events) == 1 and
                         None not in next(iter(events)))
        actual = (sequence[a], sequence[b])
        direct = pairs[actual]
        opposite = [(alleles, count) for alleles, count in pairs.items()
                    if alleles != actual and
                    count >= min_bridge_pairs and
                    unique[alleles] >= min_unique_signatures]
        contradicted = direct == 0 and bool(opposite)
        observed_bridge_count = sum(pairs.values())
        record = {
            "positions_zero_based": [a, b],
            "contig_alleles": list(actual),
            "direct_original_pair_support_for_contig_alleles": direct,
            "direct_consistent_distinct_paired_sequences_for_contig":
                unique[actual],
            "other_direct_allele_combinations": [
                {"alleles": list(alleles), "original_pairs": count,
                 "distinct_consistent_paired_sequences": unique[alleles]}
                for alleles, count in sorted(pairs.items())
                if alleles != actual],
            "contradictory_direct_link": contradicted,
            "any_original_pair_both_sites_at_q15": observed_bridge_count,
            "phase_evidence_status": (
                "direct_conflict_observed" if contradicted else
                "direct_contig_combination_observed" if direct else
                "unresolved_no_contig_allele_bridge"),
            "transitive_link_inferred": False,
            "independent_physical_molecules_inferred": False,
        }
        edges.append(record)
        if contradicted:
            contradictions.append(record["positions_zero_based"])
    return {
        "schema_version": "ivanka.original_pair_phase_veto.v1",
        "contig_length": len(sequence),
        "exact_flank_bases_per_side": anchor,
        "excluded_ambiguous_cross_contig_contexts":
            excluded_cross_contig_contexts,
        "minimum_phred_each_observed_context_base": 15,
        "original_pairs_scanned": len(records),
        "variant_sites_zero_based": variants,
        "local_q15_alleles": {
            str(pos): dict(allele_counts[pos]) for pos in variants},
        "direct_pair_observations": edges,
        "contradictory_direct_variant_pairs": contradictions,
        "withhold_contig_as_unverified_phase": bool(contradictions),
        "phase_without_direct_pair_link_is_unknown": True,
        "no_detected_conflict_does_not_validate_haplotype": True,
        "independent_physical_molecule_identity_proven": False,
        "changes_micall_max": False,
        "interpretation": (
            "Conservative direct-original-pair local-phase contradiction only. "
            "No observed bridge means UNKNOWN, not certified phase; a passing "
            "contig is not proven biologically correct."),
    }


def screen_fasta(contigs, fastq_r1, fastq_r2, *, max_pairs=50000,
                 anchor=7, min_alleles=5, min_bridge_pairs=5,
                 min_unique_signatures=3, max_contigs=16):
    if type(max_pairs) is not int or not 1 <= max_pairs <= 50000:
        raise ValueError("Bounded original paired FASTQ sample required")
    if type(max_contigs) is not int or not 1 <= max_contigs <= 1000:
        raise ValueError("Bounded number of original contigs required")
    if not contigs:
        raise ValueError("Original contig reference scope is empty")
    selected = min(max_contigs, len(contigs))
    indices, excluded = scoped_indices(contigs, selected=selected,
                                      anchor=anchor)
    pairs = []
    seen_ids = set()
    for qname, r1, r2 in iter_original_pairs(fastq_r1, fastq_r2,
                                         max_pairs=max_pairs):
        if qname in seen_ids:
            raise ValueError("Duplicate original paired FASTQ read ID")
        seen_ids.add(qname)
        pairs.append(((r1[0], r2[0]), r1, r2))
    return {
        "schema_version": "ivanka.original_pair_phase_veto_collection.v1",
        "original_pair_count": len(pairs),
        "original_qnames_deduplicated_once": True,
        "reference_scope_contig_count": len(contigs),
        "screened_contig_count": selected,
        "cross_contig_ambiguity_excluded": True,
        "exact_flank_bases_per_side": anchor,
        "results": [
            dict(contig=header, **evaluate(
                seq, pairs, anchor=anchor, min_alleles=min_alleles,
                min_bridge_pairs=min_bridge_pairs,
                min_unique_signatures=min_unique_signatures,
                exact_context_lookup=indices[i],
                excluded_cross_contig_contexts=excluded[i]))
            for i, (header, seq) in enumerate(contigs[:selected])],
        "fasta_unchanged": True,
        "source_read_pairs_are_independent_physical_molecules": False,
        "full_length_haplotype_phase_authenticated": False,
        "changes_198_acceptance": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fasta", type=Path)
    parser.add_argument("r1", type=Path)
    parser.add_argument("r2", type=Path)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--max-contigs", type=int, default=16)
    parser.add_argument("--anchor", type=int, default=7)
    parser.add_argument("--sha256-fasta", required=True)
    parser.add_argument("--sha256-r1", required=True)
    parser.add_argument("--sha256-r2", required=True)
    parser.add_argument("--min-alleles", type=int, default=5)
    parser.add_argument("--min-bridge-pairs", type=int, default=5)
    parser.add_argument("--min-unique-signatures", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = (args.fasta, args.r1, args.r2)
    hashes = (args.sha256_fasta, args.sha256_r1, args.sha256_r2)
    for source, expected in zip(paths, hashes):
        verify_source(source, expected)
    report = screen_fasta(
        fasta_records(args.fasta), args.r1, args.r2,
        max_pairs=args.max_pairs, max_contigs=args.max_contigs,
        anchor=args.anchor, min_alleles=args.min_alleles,
        min_bridge_pairs=args.min_bridge_pairs,
        min_unique_signatures=args.min_unique_signatures)
    for source, expected in zip(paths, hashes):
        verify_source(source, expected)
    report["source_sha256"] = dict(zip(("fasta", "r1", "r2"), hashes))
    report["original_sources_verified_before_and_after"] = True
    if args.output is None:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        private_output(report, args.output, paths)


if __name__ == "__main__":
    main()
