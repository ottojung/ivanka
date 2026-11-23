"""Exact original R1/R2 provenance for SAM mates with different trimming.

A SAM mate is verified only if its entire recorded sequence AND every
base quality are a contiguous substring of the corresponding original
FASTQ mate, or its reverse complement with quality order reversed.
Does not assert uniquely mapped genomic origin or DNA molecule identity.
"""
from snv_q15_evidence import reverse_complement
from snv_q15_fastq import iter_original_pairs


def exact_source_mate(row, original):
    sequence, qualities = original
    target, target_qualities = row['seq'], row['qual']
    if (not target or target == '*' or target_qualities == '*'
            or len(target) != len(target_qualities)):
        return False
    for raw_seq, raw_quality in (
        (sequence,qualities),
        (reverse_complement(sequence),qualities[::-1]),
    ):
        offset = raw_seq.find(target)
        while offset >= 0:
            if raw_quality[offset:offset+len(target)] == target_qualities:
                return True
            offset = raw_seq.find(target,offset+1)
    return False


def verified_source_pairs(r1_path,r2_path,targets,*,max_pairs=1000000):
    if not isinstance(targets,set) or not targets:
        raise ValueError('Explicit nonempty target QNAME subset required')
    if type(max_pairs) is not int or not 1 <= max_pairs <= 1000000:
        raise ValueError('Explicit bounded original pair scan required')
    found = {}
    for index,(qname,mate1,mate2) in enumerate(
        iter_original_pairs(r1_path,r2_path,max_pairs=max_pairs+1)):
        if index >= max_pairs:
            raise ValueError('Source FASTQ exceeds verified pair bound')
        if qname not in targets:
            continue
        if qname in found:
            raise ValueError('Original FASTQ contains duplicate target QNAME')
        found[qname] = {1:mate1,2:mate2}
    return found


def both_alignments_match_original(before,after,original):
    if not original:
        return False
    return all(
        exact_source_mate(before[mate],original[mate])
        and exact_source_mate(after[mate],original[mate])
        for mate in (1,2))
