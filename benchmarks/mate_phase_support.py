#!/usr/bin/env python3
"""Audit cross-mate support for phased anchor pairs lost after contig filtering.

An exact, strand-invariant anchor co-occurrence within a FASTQ pair is evidence
of association, NOT proof of insert geometry, contig attribution, a complete
haplotype, or independent source molecules. Never alters assembly or MiCall.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import gzip
import json
from pathlib import Path

from contig_diversity import read_fasta

_BASES = frozenset("ACGT")
_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def _anchor(sequence):
    if not set(sequence).issubset(_BASES):
        return None
    return min(sequence, sequence.translate(_COMPLEMENT)[::-1])


def phased_anchors(sequence, k=31, distance=300):
    """Unordered, orientation-neutral pairs of k-mers at a fixed separation."""
    if k < 1 or distance < 1:
        raise ValueError("k and distance must be positive")
    sequence = sequence.upper()
    pairs = set()
    for i in range(max(0, len(sequence) - distance - k + 1)):
        left = _anchor(sequence[i:i + k])
        right = _anchor(sequence[i + distance:i + distance + k])
        if left is not None and right is not None:
            pairs.add(tuple(sorted((left, right))))
    return pairs


def _fastq_record(handle):
    header = handle.readline()
    if not header:
        return None
    sequence, plus, quality = (handle.readline() for _ in range(3))
    if not sequence or not plus or not quality or not header.startswith("@") or not plus.startswith("+"):
        raise ValueError("malformed or truncated FASTQ record")
    sequence, quality = sequence.strip().upper(), quality.rstrip("\r\n")
    if len(sequence) != len(quality):
        raise ValueError("FASTQ sequence and quality lengths differ")
    name = header[1:].split()[0].removesuffix("/1").removesuffix("/2")
    return name, sequence, quality


def fastq_mates(first, second, max_pairs):
    if max_pairs < 1:
        raise ValueError("max_pairs must be positive")
    with ExitStack() as stack:
        paths = [Path(first), Path(second)]
        streams = [stack.enter_context(gzip.open(p, "rt") if p.suffix == ".gz" else p.open("rt")) for p in paths]
        for _ in range(max_pairs):
            records = [_fastq_record(stream) for stream in streams]
            if all(record is None for record in records):
                break
            if any(record is None for record in records):
                raise ValueError("FASTQ mates have unequal record counts")
            if records[0][0] != records[1][0]:
                raise ValueError("FASTQ mate identifiers differ")
            yield records[0][1:], records[1][1:]


def _qualified_anchors(read, quality, k, minimum_quality, interesting):
    result = set()
    failures = [ord(char) - 33 < minimum_quality for char in quality]
    failed = sum(failures[:k])
    for i in range(max(0, len(read) - k + 1)):
        if i:
            failed += failures[i + k - 1] - failures[i - 1]
        if not failed:
            anchor = _anchor(read[i:i + k])
            if anchor in interesting:
                result.add(anchor)
    return result


def audit_mate_phase(before, after, fastq1, fastq2, k=31,
                     distances=(251, 400), minimum_quality=20, max_pairs=10000):
    if k < 1 or max_pairs < 1 or not distances or any(d < 1 for d in distances):
        raise ValueError("k, max_pairs and all distances must be positive")
    if not 0 <= minimum_quality <= 93:
        raise ValueError("minimum quality must be between 0 and 93")
    lost, owners = {}, {}
    for distance in sorted(set(distances)):
        source = [phased_anchors(seq, k, distance) for seq in before]
        surviving = set().union(*(phased_anchors(seq, k, distance) for seq in after))
        lost[distance] = set().union(*source) - surviving
        owners[distance] = Counter(pair for contig in source for pair in contig)
    targets = set().union(*lost.values())
    partners = defaultdict(set)
    for a, b in targets:
        partners[a].add(b)
        partners[b].add(a)
    interesting = set(partners)
    supports = {distance: Counter() for distance in lost}
    seen = 0
    for (read1, quality1), (read2, quality2) in fastq_mates(fastq1, fastq2, max_pairs):
        seen += 1
        one = _qualified_anchors(read1, quality1, k, minimum_quality, interesting)
        two = _qualified_anchors(read2, quality2, k, minimum_quality, interesting)
        observed = {tuple(sorted((a, b))) for a in one for b in partners[a] & two}
        for distance in lost:
            supports[distance].update(observed & lost[distance])
    return {
        "sampled_read_pairs": seen,
        "k": k, "minimum_phred_quality": minimum_quality,
        "distances": {str(d): {
            "lost_anchor_pairs": len(lost[d]),
            "lost_pairs_owned_by_one_original_contig": sum(owners[d][p] == 1 for p in lost[d]),
            "lost_pairs_observed_in_at_least_1_fastq_pair": sum(supports[d][p] >= 1 for p in lost[d]),
            "lost_pairs_observed_in_at_least_3_fastq_pairs": sum(supports[d][p] >= 3 for p in lost[d]),
            "maximum_supporting_fastq_pairs": max(supports[d].values(), default=0),
        } for d in lost},
        "interpretation": ("Cross-mate exact anchor co-occurrence, counting each FASTQ pair once per signature. "
                           "No insert-size or placement verification; not proof of a full haplotype, "
                           "region attribution, or independent molecules. No consensus bases inferred."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before_fasta", type=Path)
    parser.add_argument("after_fasta", type=Path)
    parser.add_argument("fastq1", type=Path)
    parser.add_argument("fastq2", type=Path)
    parser.add_argument("--k", type=int, default=31)
    parser.add_argument("--distances", nargs="+", type=int, default=[251, 400])
    parser.add_argument("--minimum-quality", type=int, default=20)
    parser.add_argument("--max-pairs", type=int, default=10000)
    args = parser.parse_args()
    report = audit_mate_phase(read_fasta(args.before_fasta), read_fasta(args.after_fasta),
                              args.fastq1, args.fastq2, args.k, args.distances,
                              args.minimum_quality, args.max_pairs)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
