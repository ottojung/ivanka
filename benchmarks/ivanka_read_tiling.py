"""Read-supported tiling with optional overlapping sequence context."""

from math import ceil

K = 31


def tile_supported_contig(entry, depth, span=2000, min_coverage=0.8,
                          max_parts=32, overlap=0):
    """Tile from original-pair support, optionally retaining flank overlap."""
    header, sequence = entry
    length = len(sequence)
    if (span < K or span > 100000 or not 0 <= min_coverage <= 1 or
            overlap < 0 or overlap >= span):
        raise ValueError("Invalid tiling limits")
    if len(depth) != max(0, length - K + 1):
        raise ValueError("Read-depth and contig lengths disagree")
    if length <= span:
        return [entry]
    n = ceil(length / span)
    # Prevent very short fragments when a candidate barely exceeds one tile.
    # Requiring 60% of span still permits 2443nt candidates to split in two.
    if length // n < 3 * span // 5 or n > max_parts:
        return [entry]
    base, extra = divmod(length, n)
    start = 0
    parts = []
    for i in range(n):
        width = base + (i < extra)
        end = start + width
        tile_end = min(length, end + overlap)
        positions = depth[start:tile_end - K + 1]
        if (len(positions) < 1 or
                sum(v >= 3 for v in positions) <
                min_coverage * len(positions)):
            return [entry]
        parts.append((header + "_tile" + str(i + 1), sequence[start:tile_end]))
        start = end
    assert start == length
    return parts
