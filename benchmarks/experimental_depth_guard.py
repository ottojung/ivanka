"""Conservative Q15 paired-read depth guard for experimental reallocations.

Counts only the source-reference allele, once per qname and position.
Conflicting overlapping mates and nonreference bases do not inflate its depth.
This is a SAM-derived proxy, NOT MiCall's full consensus calculation. The
authentic MiCall replay must still check final calls and phase markers.
"""
import re
from collections import Counter, defaultdict

CIGAR = re.compile(r"([1-9][0-9]*)([MIDNSHP=X])")
DNA = frozenset("ACGT")


def observed_alleles(row, reference, min_q=15):
    """Return Q15 reference-position/base calls; reject unsupported geometry."""
    seq, qual = row["seq"].upper(), row["qual"]
    if not seq or len(seq) != len(qual):
        raise ValueError("Missing read or malformed qualities")
    cigar = row["cigar"]
    # Authentic MiCall remap may retain unmapped mates with CIGAR='*'.
    # They provide no coverage, even when an RNAME is present.
    if int(row["flag"]) & 0x4:
        if cigar != "*":
            raise ValueError("Unmapped mate has an alignment CIGAR")
        return {}
    if cigar == "*":
        raise ValueError("Mapped mate has no alignment CIGAR")
    tokens = CIGAR.findall(cigar)
    if not tokens or "".join(n+op for n, op in tokens) != cigar:
        raise ValueError("Invalid CIGAR")
    pos = int(row["pos"]) - 1
    if pos < 0:
        raise ValueError("Invalid SAM position")
    read_index = 0
    result = {}
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
                    result[site] = seq[index]
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


def observed_positions(row, reference, min_q=15):
    """Compatibility helper: Q15 positions irrespective of observed allele."""
    return set(observed_alleles(row, reference, min_q))


def initial_depth(rows, references, min_q=15):
    """Q15 source-REFERENCE allele depth, deduped by qname and position.

    A mismatching base does not support the source allele. If overlapping
    mates disagree at one position, that qname supports neither allele there.
    These are read-pair IDs, not independently established PCR molecules.
    """
    calls = defaultdict(dict)
    for row in rows:
        reference = references.get(row["rname"])
        if reference is None:
            continue
        name = row["qname"]
        for site, base in observed_alleles(row, reference, min_q).items():
            at_site = calls[(row["rname"], site)]
            if name not in at_site:
                at_site[name] = base
            elif at_site[name] != base:
                at_site[name] = None
    return Counter({
        key: sum(base == references[key[0]][key[1]].upper()
                 for base in per_pair.values())
        for key, per_pair in calls.items()
    })


def protected_move(pair, source, depth, references, minimum=100, min_q=15):
    """Protect source-allele Q15 depth, never merely total aligned depth."""
    reference = references[source]
    alleles = {}
    for row in pair:
        for site, base in observed_alleles(row, reference, min_q).items():
            # A source-mismatching observation or disagreeing overlapping
            # mates cannot be removed under an exact-allele depth guarantee.
            if base != reference[site].upper():
                return False
            if site in alleles and alleles[site] != base:
                return False
            alleles[site] = base
    # No qualifying source observations means no evidence to reallocate.
    if not alleles:
        return False
    # Already-undercovered source positions must never be depleted further.
    if any(depth[(source, site)] <= minimum for site in alleles):
        return False
    for site in alleles:
        if depth[(source, site)] <= 0:
            raise AssertionError("Qname allele-depth accounting underflow")
    for site in alleles:
        depth[(source, site)] -= 1
    return True
