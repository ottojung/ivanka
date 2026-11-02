"""Experimental molecule-conserving exact-template remap allocation.

Unlike copied multi-maps, this REPLACES a source pair with one exact alternate
placement. Every original qname remains exactly once with two mates. Only
source-exact, unique, phase-neutral whole templates may move. This does not
prove biological haplotype assignment; never wire into production unqualified.
"""
import csv
from collections import Counter, defaultdict

from exact_pair_remap_equivalence import lift_pair
from experimental_pair_safe_writer import checked_pair, original_orientation
from experimental_depth_guard import initial_depth, protected_move


def reallocate(original_rows, references, target, maximum_moves=None,
               maximum_span=1000, protect_depth=None):
    """Return a candidate SAM-row list and explicit molecule conservation data.

    Move at most maximum_moves distinct qnames, in original stream order.
    Original mates must be adjacent; nonadjacent/ambiguous qnames stay intact.
    Fail closed on malformed inputs rather than silently changing read pairing.
    """
    rows = list(original_rows)
    if not rows or target not in references or len(references) < 2:
        raise ValueError("Nonempty input and at least two verified references required")
    if maximum_span < 1 or (maximum_moves is not None and maximum_moves < 0):
        raise ValueError("Invalid maximum span or move budget")
    fields = tuple(rows[0])
    if any(set(row) != set(fields) for row in rows):
        raise ValueError("Inconsistent SAM fields")
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["qname"]].append(index)
    output = [dict(row) for row in rows]
    if protect_depth is not None and protect_depth < 1:
        raise ValueError("Protection depth must be positive")
    depth = (initial_depth(rows, references) if protect_depth is not None
             else None)
    stats = Counter()
    moved = {}
    for name, indices in sorted(groups.items(), key=lambda item: item[1][0]):
        if maximum_moves is not None and len(moved) >= maximum_moves:
            break
        if len(indices) != 2 or indices[1] != indices[0] + 1:
            stats["noncontiguous_or_ambiguous"] += 1
            continue
        source_pair = [rows[i] for i in indices]
        source = source_pair[0]["rname"]
        if source not in references or source == target:
            continue
        if source_pair[1]["rname"] != source:
            stats["cross_reference_source"] += 1
            continue
        candidate = lift_pair(source_pair, references, target, maximum_span)
        if candidate is None:
            stats["not_exact_compatible"] += 1
            continue
        source_checked = checked_pair(source_pair, name, source)
        target_checked = checked_pair(
            candidate, name, target, {1: source_checked[0], 2: source_checked[1]})
        if depth is not None and not protected_move(
                source_pair, source, depth, references, protect_depth):
            stats["protected_source_depth"] += 1
            continue
        by_mate = {1: target_checked[0], 2: target_checked[1]}
        # Retain original mate order even when SAM records are read2, read1.
        for i in indices:
            original = rows[i]
            mate = 1 if int(original["flag"]) & 0x40 else 2
            new = by_mate[mate]
            if original_orientation(original) != original_orientation(new):
                raise AssertionError("Observed paired FASTQ bases/qualities changed")
            output[i] = new
        moved[name] = {"from": source, "to": target}
        stats["moved_pairs"] += 1
    original_names = Counter(row["qname"] for row in rows)
    final_names = Counter(row["qname"] for row in output)
    if original_names != final_names or len(output) != len(rows):
        raise AssertionError("Molecule count or qname multiplicity changed")
    if any(original_orientation(a) != original_orientation(b)
           for a, b in zip(rows, output)):
        raise AssertionError("Original paired observations changed")
    return output, {
        "original_rows": len(rows),
        "candidate_rows": len(output),
        "original_qnames": len(original_names),
        "candidate_qnames": len(final_names),
        "moved_pairs": len(moved),
        "new_pair_ids": 0,
        "duplicated_pair_ids": 0,
        "moved_sources": dict(Counter(x["from"] for x in moved.values())),
        "rejections": dict(stats),
        "warning": "Conserved pair IDs are not proof of unbiased haplotype allocation.",
    }


def write_candidate(original_rows, references, target, output, **kwargs):
    """Validate everything before emitting a header or row."""
    result, stats = reallocate(original_rows, references, target, **kwargs)
    writer = csv.DictWriter(output, fieldnames=tuple(result[0]),
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(result)
    return stats
