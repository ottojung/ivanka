"""Read-only clipping of long, demonstrably unsupported contig termini.

No external viral sequence can enter this algorithm: the depth array is
computed exclusively by k-mer mapping against the sample's own paired FASTQs.
Only unambiguous terminal deficits are clipped, never internal gaps.
"""

K = 31


def trim_terminal_unsupported(entry, depth, min_sites=500,
                              min_fraction=0.85, min_tail=512, flank=50):
    """Return a candidate with clearly unsupported long terminal spans cut.

    Each depth element is the number of independent original read pairs
    matching a candidate 31-mer start, after repeat filtering.
    """
    header, sequence = entry
    if len(depth) != max(0, len(sequence) - K + 1):
        raise ValueError("Read-depth and contig lengths disagree")
    good = [position for position, count in enumerate(depth) if count >= 3]
    if len(good) < min_sites:
        return entry
    first, last = good[0], good[-1]
    if len(good) < min_fraction * (last - first + 1):
        return entry
    left = max(0, first - flank) if first >= min_tail + flank else 0
    right = (min(len(sequence), last + K + flank)
             if len(sequence) - (last + K) >= min_tail + flank
             else len(sequence))
    if left >= right or (left == 0 and right == len(sequence)):
        return entry
    return header, sequence[left:right]
