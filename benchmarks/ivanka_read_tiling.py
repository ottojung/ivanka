"""Lossless-in-sequence partitioning of long, densely read-supported contigs."""

from math import ceil

K = 31


def tile_supported_contig(entry, depth, span=2000, min_coverage=0.8,
                          max_parts=32):
    """Partition without overlap using only support from original read pairs."""
    header, sequence = entry
    length = len(sequence)
    if span < K or span > 100000 or not 0 <= min_coverage <= 1:
        raise ValueError("Invalid tiling limits")
    if len(depth) != max(0, length - K + 1):
        raise ValueError("Read-depth and contig lengths disagree")
    if length <= span or length < 3 * span // 2:
        return [entry]
    n = ceil(length / span)
    if n > max_parts:
        return [entry]
    base, extra = divmod(length, n)
    start = 0
    parts = []
    for i in range(n):
        width = base + (i < extra)
        end = start + width
        positions = depth[start:end - K + 1]
        if (len(positions) < 1 or
                sum(v >= 3 for v in positions) <
                min_coverage * len(positions)):
            return [entry]
        parts.append((header + "_tile" + str(i + 1), sequence[start:end]))
        start = end
    assert start == length
    return parts
