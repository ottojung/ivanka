"""Map Q15 exact local allele contexts without reference or phase imputation."""
from collections import defaultdict
from snv_q15_evidence import reverse_complement

DNA = "ACGT"


def context_index(contig, anchor=15):
    if not isinstance(contig, str) or set(contig) - set(DNA):
        raise ValueError("Contig must be resolved A/C/G/T")
    if type(anchor) is not int or anchor < 5:
        raise ValueError("Anchor must have at least five bases")
    lookup = defaultdict(set)
    for pos in range(anchor, len(contig) - anchor):
        left, right = contig[pos-anchor:pos], contig[pos+1:pos+anchor+1]
        for allele in DNA:
            kmer = left + allele + right
            lookup[kmer].add((pos, allele))
            lookup[reverse_complement(kmer)].add((pos, allele))
    # A repeated or palindromic match is not uniquely locatable.
    return {key: next(iter(locations)) for key, locations in lookup.items()
            if len(locations) == 1}


def pair_q15_calls(mate1, mate2, lookup, *, anchor=15, phred=15):
    length = 2 * anchor + 1
    calls = defaultdict(set)
    for sequence, qualities in (mate1, mate2):
        for start in range(len(sequence) - length + 1):
            window = sequence[start:start+length]
            event = lookup.get(window)
            if event is None:
                continue
            if min(ord(char) - 33 for char in
                   qualities[start:start+length]) >= phred:
                pos, allele = event
                calls[pos].add(allele)
    # Conflicting alleles in overlapping mates do not become evidence.
    return {pos: next(iter(bases)) for pos, bases in calls.items()
            if len(bases) == 1}
