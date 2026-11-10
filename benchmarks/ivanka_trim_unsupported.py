"""Read-only clipping of long, demonstrably unsupported contig termini.

No external viral sequence can enter this algorithm: the depth array is
computed exclusively by k-mer mapping against the sample's own paired FASTQs.
Only unambiguous terminal deficits are clipped, never internal gaps.
A generous 512-base flank protects true amplicon edges with no exact 31-mers.
"""

K = 31


def trim_terminal_unsupported(entry, depth, min_sites=500,
                              min_fraction=0.85, min_tail=512, flank=512):
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



def trim_supported_island(entry, depth, min_sites=500,
                          min_fraction=0.85, min_tail=512,
                          flank=512, max_gap=200):
    """Retain the broadest dense original-read-supported sequence island.

    Only activated for an explicit experiment; the conservative terminal
    trimming policy takes precedence. A long internal unobserved gap is a
    reason to examine islands separately rather than preserve a giant
    reconstructed span with no original-fragment evidence.
    """
    result = trim_terminal_unsupported(entry, depth, min_sites,
                                       min_fraction, min_tail, flank)
    if result != entry:
        return result
    header, sequence = entry
    if len(depth) != max(0, len(sequence) - K + 1):
        raise ValueError("Read-depth and contig lengths disagree")
    good = [i for i, count in enumerate(depth) if count >= 3]
    if len(good) < min_sites:
        return entry
    islands = []
    start = last = good[0]
    count = 1
    depth_sum = depth[start]
    for pos in good[1:]:
        if pos - last > max_gap:
            islands.append((start, last, count, depth_sum))
            start, count, depth_sum = pos, 0, 0
        last = pos
        count += 1
        depth_sum += depth[pos]
    islands.append((start, last, count, depth_sum))
    valid = [island for island in islands
             if island[2] >= min_sites
             and island[2] >= min_fraction * (island[1] - island[0] + 1)]
    if not valid:
        return entry
    first, last, _, _ = max(valid, key=lambda i: (i[2], i[3], -i[0]))
    left = max(0, first - flank) if first >= min_tail + flank else 0
    right = (min(len(sequence), last + K + flank)
             if len(sequence) - (last + K) >= min_tail + flank
             else len(sequence))
    if left >= right or (left == 0 and right == len(sequence)):
        return entry
    return header, sequence[left:right]
