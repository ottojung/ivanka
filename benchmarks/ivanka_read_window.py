"""Optional depth-maximizing window on a contig, using same-sample reads only."""

K = 31


def dominant_read_window(entry, depth, span=2000, min_coverage=0.8):
    """Clip a long contig to the best-supported contiguous window.

    The depth vector counts distinct original-pair 31-mer observations.
    External genomes and downstream alignment scores never enter selection.
    """
    header, sequence = entry
    if span < K or span > 100000 or not 0 <= min_coverage <= 1:
        raise ValueError("Invalid read-derived window parameters")
    if len(depth) != max(0, len(sequence) - K + 1):
        raise ValueError("Read-depth and contig lengths disagree")
    if len(sequence) <= span:
        return entry
    count = span - K + 1
    total = sum(depth[:count])
    covered = sum(d >= 3 for d in depth[:count])
    best = (total, covered, 0)
    for start in range(1, len(depth) - count + 1):
        old, new = depth[start - 1], depth[start + count - 1]
        total += new - old
        covered += (new >= 3) - (old >= 3)
        candidate = (total, covered, -start)
        if candidate > best:
            best = candidate
    start = -best[2]
    if best[1] < min_coverage * count:
        return entry
    return header, sequence[start:start + span]
