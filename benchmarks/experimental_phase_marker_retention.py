"""Conservative sequence-evidence audit for experimental MiCall final MAX A/B.

Canonical k-mers survive reverse-complement orientation changes. Only
unambiguous A/C/G/T windows count; masked x and IUPAC windows are excluded.
Retaining these markers is NECESSARY, not sufficient, for retaining haplotypes.
This does not infer molecule independence, long-range phase, or sample score.
"""
from collections import Counter

RC = str.maketrans("ACGT", "TGCA")
DNA = frozenset("ACGT")


def canonical_kmers(sequence, k):
    if k <= 0:
        raise ValueError("k must be positive")
    sequence = sequence.upper()
    result = set()
    for i in range(len(sequence) - k + 1):
        word = sequence[i:i + k]
        if set(word) <= DNA:
            reverse = word.translate(RC)[::-1]
            result.add(min(word, reverse))
    return result


def audit_phase_markers(before, after, sizes=(31, 101, 251)):
    """Count retained/lost markers per reference and across all references.

    'Unique' means present in exactly one BASELINE final-MAX region, not
    a verified native haplotype-specific marker. Never use as phase proof.
    """
    if not before or set(before) != set(after):
        raise ValueError("Both arms require the same nonempty region identities")
    if len(set(sizes)) != len(sizes) or any(k <= 0 for k in sizes):
        raise ValueError("k sizes must be distinct positive integers")
    report = {}
    for k in sizes:
        old = {r: canonical_kmers(seq, k) for r, seq in before.items()}
        new = {r: canonical_kmers(after[r], k) for r in before}
        owners = Counter(word for words in old.values() for word in words)
        pooled_old = set().union(*old.values())
        pooled_new = set().union(*new.values())
        regions = {}
        for r in sorted(before):
            unique = {word for word in old[r] if owners[word] == 1}
            regions[r] = {
                "baseline": len(old[r]),
                "candidate": len(new[r]),
                "lost": len(old[r] - new[r]),
                "gained": len(new[r] - old[r]),
                "baseline_region_unique": len(unique),
                "region_unique_lost": len(unique - new[r]),
            }
        report[str(k)] = {
            "pooled_baseline": len(pooled_old),
            "pooled_candidate": len(pooled_new),
            "pooled_lost": len(pooled_old - pooled_new),
            "pooled_gained": len(pooled_new - pooled_old),
            "all_baseline_region_markers_retained": all(
                old[r] <= new[r] for r in before),
            "regions": regions,
        }
    return {
        "sizes": report,
        "caveat": "Only canonical unambiguous k-mer retention in final MAX. "
                  "Not a proof of long-range phase, native haplotype retention, "
                  "read provenance, or independent molecules.",
    }
