#!/usr/bin/env python3
"""Audit sequence diversity retained between two assembler FASTA outputs.

This is a diagnostic, not a biological minority-haplotype or MiCall score gate.
Compare canonical k-mers so reverse-complemented contigs are not false losses.
"""
import argparse
import json
from pathlib import Path

_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def read_fasta(path):
    sequences = []
    pieces = []
    seen_header = False
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            if seen_header:
                sequences.append("".join(pieces).upper())
            pieces = []
            seen_header = True
        elif line.strip():
            if not seen_header:
                raise ValueError(f"{path}: sequence before FASTA header")
            pieces.append(line.strip())
    if seen_header:
        sequences.append("".join(pieces).upper())
    return sequences


def canonical_kmers(sequence, k=31):
    kmers = set()
    for i in range(len(sequence) - k + 1):
        window = sequence[i:i + k]
        if any(base not in "ACGT" for base in window):
            continue
        reverse = window.translate(_COMPLEMENT)[::-1]
        kmers.add(min(window, reverse))
    return kmers


def audit(before, after, k=31):
    if k < 1:
        raise ValueError("k must be positive")
    old = [s.upper() for s in before]
    new = [s.upper() for s in after]
    old_kmers = set().union(*(canonical_kmers(s, k) for s in old))
    new_kmers = set().union(*(canonical_kmers(s, k) for s in new))
    new_oriented = {min(s, s.translate(_COMPLEMENT)[::-1]) for s in new}
    retained = len(old_kmers & new_kmers)
    return {
        "k": k,
        "old_contigs": len(old),
        "new_contigs": len(new),
        "exact_old_contigs_retained": sum(
            min(s, s.translate(_COMPLEMENT)[::-1]) in new_oriented for s in old
        ),
        "old_unique_kmers": len(old_kmers),
        "new_unique_kmers": len(new_kmers),
        "old_kmers_retained": retained,
        "old_kmers_lost": len(old_kmers - new_kmers),
        "new_kmers_gained": len(new_kmers - old_kmers),
        "old_kmer_retention_fraction": retained / len(old_kmers) if old_kmers else None,
        "per_old_contig_retention_fraction": [
            (len(ks & new_kmers) / len(ks) if ks else None)
            for ks in (canonical_kmers(s, k) for s in old)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_fasta", type=Path)
    parser.add_argument("new_fasta", type=Path)
    parser.add_argument("--k", type=int, default=31)
    args = parser.parse_args()
    print(json.dumps(audit(read_fasta(args.old_fasta),
                           read_fasta(args.new_fasta), args.k), indent=2))


if __name__ == "__main__":
    main()
