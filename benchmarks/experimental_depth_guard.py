"""Conservative Q15 paired-read depth guard for experimental reallocations.

Counts a qname at most once per reference position, even when mates overlap.
This is a SAM-derived proxy, NOT MiCall's full consensus calculation. The
authentic MiCall replay must still check final calls and phase markers.
"""
import re
from collections import Counter, defaultdict

CIGAR = re.compile(r"([1-9][0-9]*)([MIDNSHP=X])")
DNA = frozenset("ACGT")


def observed_positions(row, reference, min_q=15):
    """Return Q15 reference coordinates; reject unsupported CIGAR or geometry."""
    seq, qual = row["seq"].upper(), row["qual"]
    if not seq or len(seq) != len(qual):
        raise ValueError("Missing read or malformed qualities")
    cigar = row["cigar"]
    # Authentic MiCall remap can retain unmapped mates with an RNAME and
    # CIGAR='*'. They contribute no reference coverage and are never movable.
    if int(row["flag"]) & 0x4:
        if cigar != "*":
            raise ValueError("Unmapped mate has an alignment CIGAR")
        return set()
    if cigar == "*":
        raise ValueError("Mapped mate has no alignment CIGAR")
    tokens = CIGAR.findall(cigar)
    if not tokens or "".join(n+op for n, op in tokens) != cigar:
        raise ValueError("Invalid CIGAR")
    pos = int(row["pos"]) - 1
    if pos < 0:
        raise ValueError("Invalid SAM position")
    read_index = 0
    result = set()
    for n, op in tokens:
        n = int(n)
        if op in "M=X":
            for offset in range(n):
                index = read_index + offset
                site = pos + offset
                if (site < 0 or site >= len(reference)
                        or index >= len(seq)):
                    raise ValueError("Alignment extends beyond read/reference")
                if seq[index] in DNA and ord(qual[index]) - 33 >= min_q:
                    result.add(site)
            pos += n
            read_index += n
        elif op in "IS":
            read_index += n
        elif op in "DN":
            pos += n
        elif op in "HP":
            pass
    if read_index != len(seq):
        raise ValueError("CIGAR does not consume the complete observed read")
    return result


def initial_depth(rows, references, min_q=15):
    """Distinct qname depth at each reference coordinate, not independent PCR molecules."""
    seen = defaultdict(set)
    for row in rows:
        reference = references.get(row["rname"])
        if reference is None:
            continue
        name = row["qname"]
        for site in observed_positions(row, reference, min_q):
            seen[(row["rname"], site)].add(name)
    return Counter({key: len(names) for key, names in seen.items()})


def protected_move(pair, source, depth, references, minimum=100, min_q=15):
    """Disallow removing a qname when its source Q15 depth would cross 100."""
    sites = set().union(*(observed_positions(row, references[source], min_q)
                          for row in pair))
    # Already-undercovered source positions must never be depleted further.
    if any(depth[(source, site)] <= minimum for site in sites):
        return False
    for site in sites:
        if depth[(source, site)] <= 0:
            raise AssertionError("Qname depth accounting underflow")
    for site in sites:
        depth[(source, site)] -= 1
    return True
