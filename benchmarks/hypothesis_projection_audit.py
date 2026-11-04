"""Read-only integrity proof for conditional HCV read-pair projections.

A pair may support two alternative contigs, but must occur only once within
each target. No independent-molecule inference is made from shared evidence.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

_SUFFIX = "|ivanka_hypothesis="
_HCV = re.compile(r"^\d+-(HCV-\d+[a-z])$")


def _references(path):
    refs = {}
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            name, seq = row["region"], row["sequence"].upper()
            if name in refs:
                raise ValueError("duplicate reference name")
            refs[name] = seq
    return refs


def _window(row, reference):
    cigar = re.fullmatch(r"(?:([1-9]\d*)S)?([1-9]\d*)M(?:([1-9]\d*)S)?", row["cigar"])
    if cigar is None:
        raise ValueError("unsupported projected CIGAR")
    prefix, count, suffix = (int(x or 0) for x in cigar.groups())
    length = len(row["seq"])
    if prefix + count + suffix != length or len(row["qual"]) != length:
        raise ValueError("projected sequence or quality length mismatch")
    try:
        start = int(row["pos"]) - 1
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid projected alignment position") from exc
    if start < 0 or start + count > len(reference):
        raise ValueError("projected alignment exceeds reference")
    return reference[start:start + count]


def _neighbors(refs, name):
    source = refs[name]
    match = _HCV.fullmatch(name)
    if not match or len(source) < 1000 or set(source) - set("ACGT"):
        return []
    result = []
    for other, sequence in refs.items():
        hit = _HCV.fullmatch(other)
        if (other == name or not hit or hit.group(1) != match.group(1)
                or len(sequence) != len(source) or set(sequence) - set("ACGT")):
            continue
        differences = sum(a != b for a, b in zip(source, sequence))
        if 0 < differences <= min(20, len(source) // 100):
            result.append(other)
    return sorted(result)


def audit_projection(original_path, projected_path, references_path):
    """Reject any fabricated row, cross-target duplication or unsafe placement."""
    refs = _references(references_path)
    neighbor_cache = {}

    def neighbors(name):
        if name not in neighbor_cache:
            neighbor_cache[name] = _neighbors(refs, name)
        return neighbor_cache[name]

    originals = {}
    original_count = 0
    with Path(original_path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        if not fields or not {"qname", "flag", "rname", "pos", "cigar", "rnext",
                              "pnext", "tlen", "seq", "qual"} <= set(fields):
            raise ValueError("missing original SAM-like fields")
        for row in reader:
            originals.setdefault(row["qname"], []).append(row)
            original_count += 1
    counts = Counter()
    observed_flags = {}
    with Path(projected_path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != fields:
            raise ValueError("projected remap columns differ")
        # Original entries must be present in their original order.
        with Path(original_path).open(newline="") as source:
            original_rows = csv.DictReader(source)
            for expected in original_rows:
                actual = next(reader, None)
                if actual != expected:
                    raise ValueError("an original mapping was removed or modified")
        for row in reader:
            name, sep, target = row["qname"].partition(_SUFFIX)
            if not sep or not name or not target or row["rname"] != target:
                raise ValueError("unrecognized additional mapping")
            original_pair = originals.get(name, [])
            if len(original_pair) != 2 or row["qname"] in originals:
                raise ValueError("projection lacks a unique original pair")
            sources = {r["rname"] for r in original_pair}
            if len(sources) != 1:
                raise ValueError("original pair maps to multiple references")
            source_name = next(iter(sources))
            try:
                coordinates = [int(m["pos"]) for m in original_pair]
                mates_at = [int(m["pnext"]) for m in original_pair]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("invalid original mate coordinates") from exc
            if any(p < 0 or (p and p != coordinates[1-i])
                   for i, p in enumerate(mates_at)):
                raise ValueError("contradictory original mate coordinates")
            if (source_name not in refs or target not in refs or
                    neighbors(source_name) != [target] or
                    neighbors(target) != [source_name]):
                raise ValueError("target is not an isolated reciprocal hypothesis")
            mates = [r for r in original_pair if r["flag"] == row["flag"]]
            if len(mates) != 1:
                raise ValueError("projected mate is ambiguous")
            original = mates[0]
            reconstructed = dict(original)
            reconstructed["qname"], reconstructed["rname"] = row["qname"], target
            if reconstructed["rnext"] == source_name:
                reconstructed["rnext"] = target
            if row != reconstructed:
                raise ValueError("projected bases, qualities or metadata were modified")
            if _window(original, refs[source_name]) != _window(row, refs[target]):
                raise ValueError("projected interval differs across hypotheses")
            counts[(name, target)] += 1
            observed_flags.setdefault((name, target), set()).add(int(row["flag"]))
    if any(count != 2 or observed_flags[key] not in ({99, 147}, {83, 163})
           for key, count in counts.items()):
        raise ValueError("a pair is duplicated or malformed within one target")
    return {
        "original_mapping_rows": original_count,
        "extra_conditional_mapping_rows": sum(counts.values()),
        "extra_conditional_pairs": len(counts),
        "cross_target_duplicate_pairs": 0,
        "independent_molecules_claimed": False,
        "interpretation": "Shared read-pair observations are conditional on each separate contig, not independent molecules across contigs",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_remap", type=Path)
    parser.add_argument("projected_remap", type=Path)
    parser.add_argument("remap_references", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_projection(args.original_remap, args.projected_remap,
                                      args.remap_references), indent=2))


if __name__ == "__main__":
    main()
