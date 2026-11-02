"""Read-only original-FASTQ cross-check for directly observed local alleles.

Exact substring support is NOT unique genomic placement, haplotype phase,
independent molecules, or permission to change MiCall consensus calls.
"""
import argparse
import gzip
import json
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

BASES = frozenset("ACGT")
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def fastq_records(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as stream:
        while True:
            header = stream.readline()
            if not header:
                return
            sequence = stream.readline().strip().upper()
            plus = stream.readline()
            quality = stream.readline().strip()
            if (not header.startswith("@") or not plus.startswith("+")
                    or not sequence or len(sequence) != len(quality)
                    or set(sequence) - (BASES | {"N"})):
                raise ValueError("Malformed FASTQ record")
            name = header[1:].split()[0]
            if name.endswith(("/1", "/2")):
                name = name[:-2]
            if not name:
                raise ValueError("Empty FASTQ identifier")
            yield name, sequence, quality


def contains_quality_allele(sequence, quality, allele, minimum_quality):
    """Require every observed base of an exact allele to pass the Q cutoff."""
    for motif in {allele, reverse_complement(allele)}:
        offset = sequence.find(motif)
        while offset != -1:
            if all(ord(q) - 33 >= minimum_quality
                   for q in quality[offset:offset + len(motif)]):
                return True
            offset = sequence.find(motif, offset + 1)
    return False


def audit_original_pairs(read1, read2, alleles, minimum_quality=15):
    """Count raw paired-read records and distinct exact paired sequences.

    Each pair is counted once even when both mates observe the allele.
    A pair supporting two listed alleles is conflicting, never counted for
    either. Repeated paired sequences are one diversity signature, with
    contradictory or low-quality duplicates conservatively excluded.
    """
    if (minimum_quality < 0 or not alleles
            or any(not a or set(a) - BASES for a in alleles)
            or len({min(a, reverse_complement(a)) for a in alleles})\n               != len(alleles)):
        raise ValueError("Invalid allele set or quality cutoff")
    counts = Counter()
    signatures = defaultdict(set)
    seen_names = set()
    total = conflicts = 0
    for first, second in zip_longest(fastq_records(read1),
                                     fastq_records(read2)):
        if first is None or second is None or first[0] != second[0]:
            raise ValueError("FASTQ mates missing or out of order")
        name = first[0]
        if name in seen_names:
            raise ValueError("Repeated FASTQ pair identifier")
        seen_names.add(name)
        total += 1
        observed = {
            allele for allele in alleles
            if any(contains_quality_allele(seq, qual, allele, minimum_quality)
                   for _, seq, qual in (first, second))
        }
        signature = (first[1], second[1])
        if len(observed) == 1:
            allele = next(iter(observed))
            counts[allele] += 1
            signatures[signature].add(allele)
        else:
            if observed:
                conflicts += 1
            signatures[signature].add(None)
    distinct = Counter()
    for states in signatures.values():
        if len(states) == 1 and None not in states:
            distinct[next(iter(states))] += 1
    return {
        "read_pairs": total,
        "minimum_phred": minimum_quality,
        "allele_support_pair_ids": {a: counts[a] for a in alleles},
        "allele_distinct_pair_sequences": {a: distinct[a] for a in alleles},
        "conflicting_pair_ids": conflicts,
        "interpretation": "Exact raw read substrings only; no locus assignment, "
                          "phase, independent molecule count, or MiCall correction.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("read1", type=Path)
    parser.add_argument("read2", type=Path)
    parser.add_argument("--allele", action="append", required=True)
    parser.add_argument("--min-phred", type=int, default=15)
    args = parser.parse_args()
    print(json.dumps(audit_original_pairs(
        args.read1, args.read2, [a.upper() for a in args.allele],
        args.min_phred), indent=2))


if __name__ == "__main__":
    main()
