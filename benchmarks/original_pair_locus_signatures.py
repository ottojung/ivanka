"""Quality-consistent exact R1+R2 sequence signatures for each local locus.

A duplicate sequence is NOT an independently sampled physical DNA molecule.
For local quality evidence, every original paired ID with that exact same
R1+R2 sequence must agree on the same nonmissing Q15 central allele.
"""
from collections import Counter, defaultdict


def consistent_locus_signatures(records):
    copies = Counter(signature for signature, _ in records)
    observed = defaultdict(dict)
    for signature, calls in records:
        for gid, allele in calls.items():
            old = observed[gid].get(signature)
            if old is None:
                observed[gid][signature] = [allele, 1, True]
            else:
                old[1] += 1
                old[2] &= old[0] == allele
    result = defaultdict(Counter)
    for gid, by_signature in observed.items():
        for signature, (allele, n, consistent) in by_signature.items():
            if consistent and n == copies[signature]:
                result[gid][allele] += 1
    return result
