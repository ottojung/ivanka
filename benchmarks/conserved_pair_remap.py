"""Opt-in, reference-consistent HCV read-pair sharing between contig hypotheses.

The same original read pair may support one reciprocal alternative only
when both mates align to exactly identical reference sequence on each.
One observation contributes once per hypothesis, never independent molecules.
Multi-haplotype groups are explicitly excluded because they can change already
called minor alleles (observed in genuine MidHCV S11).
This is NOT a global abundance estimate or a full haplotype proof.

Production MiCall must remain unchanged unless an explicitly experimental
candidate image installs this module at the remap -> sam2aln boundary.
"""
from collections import Counter
import csv
import os
from pathlib import Path
import re
import tempfile

_DNA = frozenset("ACGT")
_FLAGS = ({83, 163}, {99, 147})
_TARGET_SUFFIX = "|ivanka_hypothesis="
_HCV_REGION = re.compile(r"^\d+-(HCV-\d+[a-z])$")


def load_references(path):
    refs = {}
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            name, sequence = row["region"], row["sequence"].upper()
            if name in refs:
                raise ValueError("duplicate remapping reference")
            if _HCV_REGION.fullmatch(name) and set(sequence) <= _DNA:
                refs[name] = sequence
    return refs


def compatible_groups(refs):
    """Only isolated reciprocal pairs; multi-hypothesis sharing can alter alleles."""
    neighbors = {}
    for name, source in refs.items():
        suffix = _HCV_REGION.fullmatch(name).group(1)
        neighbors[name] = sorted(target for target, other in refs.items()
            if target != name and len(source) == len(other) and len(source) >= 1000
            and _HCV_REGION.fullmatch(target).group(1) == suffix
            and 0 < sum(a != b for a, b in zip(source, other))
            <= min(20, len(source) // 100))
    return {name: targets for name, targets in neighbors.items()
            if len(targets) == 1 and neighbors[targets[0]] == [name]}


def mapped_window(row, expected_ref, reference_length):
    """Reference interval of one M block, optionally with terminal S clips."""
    if row["rname"] != expected_ref or row["rnext"] not in ("=", expected_ref):
        return None
    cigar = row["cigar"]
    # Only terminal soft clips are SAM-valid for a single contiguous M block.
    # Reject internal clips, repeated clips and zero-length operations rather
    # than projecting a malformed mapping into another haplotype.
    if not re.fullmatch(r"(?:[1-9]\d*S)?[1-9]\d*M(?:[1-9]\d*S)?", cigar):
        return None
    ops = re.findall(r"(\d+)([MS])", cigar)
    matches = [int(n) for n, op in ops if op == "M"]
    if sum(int(n) for n, _ in ops) != len(row["seq"]):
        return None
    if len(row["qual"]) != len(row["seq"]):
        return None
    try:
        start = int(row["pos"]) - 1
    except (ValueError, TypeError):
        return None
    length = matches[0]
    if start < 0 or start + length > reference_length:
        return None
    return start, start + length


def compatible_targets(mates, refs, groups):
    if len(mates) != 2 or not mates[0]["qname"] or mates[0]["qname"] != mates[1]["qname"]:
        return []
    source = mates[0]["rname"]
    if source not in groups or any(r["rname"] != source for r in mates):
        return []
    try:
        flags = {int(r["flag"]) for r in mates}
    except (ValueError, TypeError):
        return []
    if flags not in _FLAGS:
        return []
    # A populated SAM PNEXT must point to the actual mate, not a third
    # alignment with the same QNAME. MiCall remaps can leave PNEXT at zero.
    try:
        positions = [int(row["pos"]) for row in mates]
        mate_positions = [int(row["pnext"]) for row in mates]
    except (ValueError, TypeError, KeyError):
        return []
    if any(p < 0 or (p and p != positions[1 - i])
           for i, p in enumerate(mate_positions)):
        return []
    windows = [mapped_window(row, source, len(refs[source])) for row in mates]
    if any(window is None for window in windows):
        return []
    sequence = refs[source]
    return [target for target in groups[source]
            if all(sequence[a:b] == refs[target][a:b] for a, b in windows)]


def project_remap(remap_path, reference_path, output_path):
    """Return (effective_remap_path, stats); original input is never changed."""
    remap_path = Path(remap_path)
    output_path = Path(output_path)
    if remap_path.resolve() == output_path.resolve():
        raise ValueError("remap input and output must be separate")
    refs = load_references(reference_path)
    groups = compatible_groups(refs)
    if not groups:
        return remap_path, {"groups": 0, "projected_pairs": 0}
    counts = Counter()
    with remap_path.open(newline="") as original:
        reader = csv.DictReader(original)
        fields = reader.fieldnames
        if not fields or not {"qname", "flag", "rname", "pos", "cigar", "rnext", "seq", "qual"} <= set(fields):
            raise ValueError("missing SAM-like remap columns")
        for row in reader:
            counts[row["qname"]] += 1
    projected = Counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", newline="", dir=output_path.parent,
                                     prefix="ivanka-remap-", suffix=".csv", delete=False) as temp:
        intermediate = Path(temp.name)
        writer = csv.DictWriter(temp, fields, lineterminator="\n")
        try:
            writer.writeheader()
            with remap_path.open(newline="") as original:
                writer.writerows(csv.DictReader(original))
            # Reopen to avoid holding all read records in memory.
            pending = {}
            with remap_path.open(newline="") as original:
                for row in csv.DictReader(original):
                    name = row["qname"]
                    if counts[name] != 2 or _TARGET_SUFFIX in name:
                        continue
                    first = pending.pop(name, None)
                    if first is None:
                        pending[name] = row
                        continue
                    for target in compatible_targets((first, row), refs, groups):
                        projected_name = name + _TARGET_SUFFIX + target
                        if projected_name in counts:
                            continue
                        for mate in (first, row):
                            copy = dict(mate)
                            copy["qname"] = projected_name
                            copy["rname"] = target
                            if copy["rnext"] == first["rname"]:
                                copy["rnext"] = target
                            writer.writerow(copy)
                        projected[target] += 1
        except BaseException:
            intermediate.unlink(missing_ok=True)
            raise
    os.replace(intermediate, output_path)
    return output_path, {
        "groups": len(groups), "projected_pairs": sum(projected.values()),
        "projected_pairs_per_reference": dict(sorted(projected.items())),
    }
