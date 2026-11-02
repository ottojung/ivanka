"""Safely serialize *hypothetical* alternative SAM pairs for MiCall.

Every alternative is a pair-compatible multi-mapping of an existing read,
not an independent molecule. No source files are modified by this module.
Call only with alternate pairs already verified against exact entire templates.
"""
import csv
from collections import Counter, defaultdict

def _validate_pair(rows, qname, reference):
    if len(rows) != 2:
        raise ValueError(f"{qname}/{reference}: must contain exactly two mates")
    flags = [int(r["flag"]) for r in rows]
    if any(r["qname"] != qname or r["rname"] != reference for r in rows):
        raise ValueError("Mixed qname/reference within an alternative pair")
    if (sum(bool(f & 0x40) for f in flags) != 1
            or sum(bool(f & 0x80) for f in flags) != 1
            or any(f & (0x4 | 0x8 | 0x100 | 0x800) for f in flags)):
        raise ValueError("Missing, ambiguous, secondary or supplementary mate")
    for row, mate in ((rows[0], rows[1]), (rows[1], rows[0])):
        if row["pnext"] != mate["pos"] or row["rnext"] not in ("=", reference):
            raise ValueError("Inconsistent mate coordinates/reference")
        if row["mapq"] != "0":
            raise ValueError("Alternative map must have MAPQ zero")
    return sorted(rows, key=lambda r: bool(int(r["flag"]) & 0x80))


def serialize_original_then_alternatives(original, alternatives, output):
    """Preserve original order, insert each proven pair immediately after its
    final original mate, preventing MiCall's qname-only matchmaker from
    cross-pairing the candidate reference and the source reference.
    """
    original = list(original)
    alternatives = list(alternatives)
    if not original:
        raise ValueError("Missing original remap records")
    fields = list(original[0])
    if any(set(row) != set(fields) for row in original + alternatives):
        raise ValueError("SAM CSV columns differ")
    occurrences = Counter(row["qname"] for row in original)
    source_refs = defaultdict(set)
    for row in original:
        source_refs[row["qname"]].add(row["rname"])
    groups = defaultdict(list)
    for row in alternatives:
        groups[(row["qname"], row["rname"])].append(row)
    appended = defaultdict(list)
    for (name, target), rows in groups.items():
        if occurrences[name] != 2 or len(source_refs[name]) != 1:
            raise ValueError("Original pair missing or multiply mapped")
        if target in source_refs[name]:
            raise ValueError("Alternative duplicates original reference")
        appended[name].extend(_validate_pair(rows, name, target))
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in original:
        writer.writerow(row)
        name = row["qname"]
        occurrences[name] -= 1
        if occurrences[name] == 0:
            writer.writerows(appended.get(name, ()))
    return {"original_rows": len(original), "alternative_rows": len(alternatives),
            "alternative_pair_refs": len(groups),
            "total_rows": len(original) + len(alternatives)}
