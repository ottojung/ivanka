"""Conservative unique-source exact flank lookup across all input contigs.

Even synthetic alternate allele contexts must be absent from other contigs'
possible single-base local contexts; identical contexts do not identify which
contig generated the original read. False negatives are safer than fake phase.
"""
from collections import defaultdict

from original_pair_phase_calls import context_index
from snv_q15_evidence import reverse_complement


def scoped_indices(contigs, *, selected, anchor):
    if not contigs or not 1 <= selected <= len(contigs):
        raise ValueError("Require a nonempty reference contig scope")
    indices = [context_index(seq, anchor=anchor)
               for _, seq in contigs[:selected]]
    owners = defaultdict(set)
    for i, index in enumerate(indices):
        for kmer in index:
            owners[kmer].add(i)
    blocked = [set() for _ in indices]
    for kmer, sites in owners.items():
        if len(sites) > 1:
            for i in sites:
                blocked[i].add(kmer)
    for source_i, (_, sequence) in enumerate(contigs):
        for pos in range(anchor, len(sequence)-anchor):
            left, right = sequence[pos-anchor:pos], (
                sequence[pos+1:pos+anchor+1])
            for allele in "ACGT":
                pattern = left + allele + right
                for kmer in (pattern, reverse_complement(pattern)):
                    for target_i in owners.get(kmer, ()):
                        if target_i != source_i:
                            blocked[target_i].add(kmer)
    return [{k: event for k, event in index.items()
             if k not in excluded}
            for index, excluded in zip(indices, blocked)], [
                len(items) for items in blocked]
