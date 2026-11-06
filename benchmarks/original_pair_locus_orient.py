"""Canonicalize local flanks without conflating strand and allele identity."""
from snv_q15_evidence import reverse_complement

_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def canonical_flanks(left, right):
    forward = (left, right)
    reverse = (reverse_complement(right), reverse_complement(left))
    if forward == reverse:
        # No uniquely orientable central base in a symmetric flank group.
        return None, None
    return (forward, False) if forward < reverse else (reverse, True)


def canonical_allele(base, reverse):
    return base.translate(_COMPLEMENT) if reverse else base
