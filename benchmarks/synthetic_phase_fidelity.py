#!/usr/bin/env python3
"""Fail-closed exact-anchor phasing audit for synthetic known-truth contigs.

Original paired-read linkage comes from the synthetic truth's known geometry;
this cannot assess unknown clinical haplotypes or independent molecules.
"""
import argparse
import json
from pathlib import Path

from synthetic_phase_pairs import DNA, reverse_complement


def fasta_records(path):
    records = []
    header, pieces = None, []
    for raw in Path(path).read_text().splitlines():
        if raw.startswith(">"):
            if header is not None:
                records.append((header, "".join(pieces).upper()))
            header, pieces = raw[1:], []
        elif header is None:
            raise ValueError("FASTA sequence before header")
        else:
            pieces.append(raw.strip())
    if header is not None:
        records.append((header, "".join(pieces).upper()))
    if not records:
        raise ValueError("FASTA contains no contigs")
    return records


def anchored_allele(contig, reference, position, anchor=25):
    """Only report one exact, uniquely aligned local SNP; never impute gaps."""
    if (anchor < 1 or position < anchor or
            position + anchor >= len(reference)):
        return None
    left = reference[position-anchor:position]
    right = reference[position+1:position+1+anchor]
    hits = [(base, contig.count(left+base+right)) for base in DNA]
    return (next(base for base, count in hits if count)
            if sum(count for _, count in hits) == 1 else None)


def analyze(truth, contigs, anchor=25):
    positions = truth["variant_positions_zero_based"]
    coupled = truth["phase_coupled_haplotypes"]
    if len(positions) != 2 or len(coupled) != 2:
        raise ValueError("Expected exactly two synthetic phased variants")
    reference = coupled[0]
    real_phases = {tuple(h[position] for position in positions)
                   for h in coupled}
    bridges = truth["read_pairs_directly_observing_both_variants"]
    rows = []
    for header, sequence in contigs:
        candidates = []
        for orientation, oriented in (("+", sequence),
                                      ("-", reverse_complement(sequence))):
            calls = tuple(anchored_allele(oriented, reference, position, anchor)
                          for position in positions)
            if all(base is not None for base in calls):
                candidates.append((orientation, calls))
        if len(candidates) != 1:
            status = "unresolved_or_ambiguous"
            orientation, calls = None, (None, None)
        else:
            orientation, calls = candidates[0]
            if bridges == 0:
                status = "unidentifiable_phase"
            elif calls not in real_phases:
                status = "unsupported_recombinant"
            else:
                status = "consistent_with_source_phase"
        rows.append({"contig": header, "length": len(sequence),
                     "orientation": orientation, "allele_calls": list(calls),
                     "classification": status})
    return {
        "synthetic_only": True,
        "read_pairs_directly_observing_both_variants": bridges,
        "true_coupled_allele_pairs": [list(p) for p in sorted(real_phases)],
        "contigs": rows,
        "unsupported_recombinant_count":
            sum(r["classification"] == "unsupported_recombinant" for r in rows),
        "unidentifiable_phase_count":
            sum(r["classification"] == "unidentifiable_phase" for r in rows),
        "interpretation": (
            "A recombinant call is absent from either generating haplotype "
            "despite original pairs directly observing both variants. "
            "No-bridge calls are unidentifiable even if matching known truth. "
            "Exact flanks are required; unresolved calls prove nothing. "
            "This is synthetic-only and not clinical validation."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("truth_json", type=Path)
    parser.add_argument("assembled_fasta", type=Path)
    parser.add_argument("--anchor", type=int, default=25)
    args = parser.parse_args()
    result = analyze(json.loads(args.truth_json.read_text()),
                     fasta_records(args.assembled_fasta), args.anchor)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
