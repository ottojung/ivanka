#!/usr/bin/env python3
"""Audit sequence diversity retained between two assembler FASTA outputs.

This is a diagnostic, not a biological minority-haplotype or MiCall score gate.
Compare canonical k-mers so reverse-complemented contigs are not false losses.
"""
import argparse
from collections import Counter
import gzip
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


def _fastq_sequences(path, max_records):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for _ in range(max_records):
            header = stream.readline()
            if not header:
                break
            bases = stream.readline().strip().upper()
            plus = stream.readline()
            quality = stream.readline().strip()
            if not header.startswith("@") or not plus.startswith("+") or len(bases) != len(quality):
                raise ValueError(f"{path}: invalid/truncated FASTQ record")
            yield bases


def read_record_support(read_paths, target_kmers, k=31, max_records=10000):
    """Count exact canonical k-mers once per sampled FASTQ *record*, not molecule."""
    if k < 1 or max_records < 1:
        raise ValueError("k and max_records must be positive")
    support = Counter()
    sampled = []
    for path in read_paths:
        count = 0
        for bases in _fastq_sequences(path, max_records):
            support.update(canonical_kmers(bases, k) & target_kmers)
            count += 1
        sampled.append(count)
    if len(sampled) != 2 or sampled[0] != sampled[1] or sampled[0] == 0:
        raise ValueError("Two nonempty FASTQ mates must have equal sampled record counts")
    return support, sum(sampled)


def read_supported_loss(before, after, read_paths, k=31, max_records=10000):
    """Supplement sequence-diversity loss with independent FASTQ-record counts."""
    old = set().union(*(canonical_kmers(s.upper(), k) for s in before))
    new = set().union(*(canonical_kmers(s.upper(), k) for s in after))
    lost = old - new
    support, sampled = read_record_support(read_paths, lost, k, max_records)
    values = [support[x] for x in lost]
    return {
        "sampled_read_records": sampled,
        "max_records_per_mate": max_records,
        "lost_unique_kmers": len(lost),
        "lost_kmers_supported_by_at_least_1_record": sum(n >= 1 for n in values),
        "lost_kmers_supported_by_at_least_3_records": sum(n >= 3 for n in values),
        "lost_kmers_supported_by_at_least_10_records": sum(n >= 10 for n in values),
        "lost_kmers_supported_by_at_least_100_records": sum(n >= 100 for n in values),
        "warning": "Read-record support does not establish independent molecules or phasing",
    }


def canonical_linkages(sequence, k=31, distance=100):
    """Exact ordered pairs of k-mer anchors, canonicalized across both strands.

    The intervening bases are *not* compared: these are within-read linkage
    observations, not proof of an entire haplotype or independent molecules.
    """
    if k < 1 or distance < 1:
        raise ValueError("k and anchor distance must be positive")
    sequence = sequence.upper()
    result = set()
    for i in range(max(0, len(sequence) - distance - k + 1)):
        first = sequence[i:i + k]
        second = sequence[i + distance:i + distance + k]
        if any(base not in "ACGT" for base in first + second):
            continue
        reverse = (second.translate(_COMPLEMENT)[::-1],
                   first.translate(_COMPLEMENT)[::-1])
        result.add(min((first, second), reverse))
    return result


def read_linkage_loss(before, after, read_paths, k=31,
                      distances=(100, 200), max_records=10000):
    """Audit read-backed phase linkages absent from the candidate contigs.

    A linkage joins two exact k-mer anchors at a fixed separation within one
    FASTQ record. Neither marginal k-mer support nor read linkage proves a
    full-length minority haplotype; no reference or aligner is involved.
    """
    if k < 1 or max_records < 1 or not distances or any(d < 1 for d in distances):
        raise ValueError("k, max_records and every distance must be positive")
    distances = sorted(set(distances))
    lost = {}
    for distance in distances:
        old = set().union(*(canonical_linkages(s, k, distance) for s in before))
        new = set().union(*(canonical_linkages(s, k, distance) for s in after))
        lost[distance] = old - new
    support = {distance: Counter() for distance in distances}
    sampled = []
    for path in read_paths:
        count = 0
        for bases in _fastq_sequences(path, max_records):
            for distance in distances:
                if lost[distance]:
                    support[distance].update(
                        canonical_linkages(bases, k, distance) & lost[distance])
            count += 1
        sampled.append(count)
    if len(sampled) != 2 or sampled[0] != sampled[1] or sampled[0] == 0:
        raise ValueError("Two nonempty FASTQ mates must have equal sampled record counts")
    return {
        "sampled_read_records": sum(sampled),
        "k": k,
        "distances": {
            str(d): {
                "lost_linkages": len(lost[d]),
                "lost_linkages_supported_by_at_least_1_record":
                    sum(support[d][x] >= 1 for x in lost[d]),
                "lost_linkages_supported_by_at_least_3_records":
                    sum(support[d][x] >= 3 for x in lost[d]),
                "lost_linkages_supported_by_at_least_10_records":
                    sum(support[d][x] >= 10 for x in lost[d]),
                "max_supporting_read_records":
                    max((support[d][x] for x in lost[d]), default=0),
            } for d in distances
        },
        "warning": "Exact within-read anchor linkage is not full-haplotype or independent-molecule support",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_fasta", type=Path)
    parser.add_argument("new_fasta", type=Path)
    parser.add_argument("--k", type=int, default=31)
    parser.add_argument("--reads1", type=Path)
    parser.add_argument("--reads2", type=Path)
    parser.add_argument("--max-read-records", type=int, default=10000,
                        help="Sample at most this many FASTQ records from each mate")
    parser.add_argument("--link-distances", type=int, nargs="+",
                        help="Audit read-backed ordered 31-mer anchor pairs at these separations; requires both FASTQs")
    args = parser.parse_args()
    if (args.reads1 is None) != (args.reads2 is None):
        parser.error("--reads1 and --reads2 must be supplied together")
    if args.link_distances and args.reads1 is None:
        parser.error("--link-distances requires --reads1 and --reads2")
    before = read_fasta(args.old_fasta)
    after = read_fasta(args.new_fasta)
    report = audit(before, after, args.k)
    if args.reads1 is not None:
        report["lost_kmer_read_record_support"] = read_supported_loss(
            before, after, [args.reads1, args.reads2], args.k, args.max_read_records)
    if args.link_distances:
        report["lost_read_linkages"] = read_linkage_loss(
            before, after, [args.reads1, args.reads2],
            k=args.k, distances=args.link_distances, max_records=args.max_read_records)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
