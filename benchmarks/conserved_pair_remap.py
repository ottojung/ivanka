"""Opt-in, molecule-conserving HCV hypothesis read-pair reassignment.

Each read pair is retained once with its original identifier. A transfer is
allowed only where both mates have compatible reference intervals and the
source retains conservative Q15 depth estimated from read-pair observations.
This is NOT a global abundance estimate or a full haplotype proof.

Production MiCall must remain unchanged unless an explicitly experimental
candidate image installs this module at the remap -> sam2aln boundary.
"""
from collections import Counter, defaultdict
import csv
import os
from pathlib import Path
import re
import tempfile

_DNA = frozenset("ACGT")
_FLAGS = ({83, 163}, {99, 147})
_SOURCE_Q15_RESERVE = 110
_TARGET_Q15_GUIDE = 120
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
    """Group same-length, nearly identical, unambiguous HCV alternatives."""
    groups = {}
    for name, source in refs.items():
        suffix = _HCV_REGION.fullmatch(name).group(1)
        options = []
        for target, other in refs.items():
            if (target == name or len(source) != len(other) or len(source) < 1000
                    or _HCV_REGION.fullmatch(target).group(1) != suffix):
                continue
            differences = sum(a != b for a, b in zip(source, other))
            if 0 < differences <= min(20, len(source) // 100):
                options.append(target)
        # Skip enormous ambiguity groups rather than exploding runtime.
        if 1 <= len(options) <= 4:
            groups[name] = sorted(options)
    return groups


def mapped_window(row, expected_ref, reference_length):
    """Reference interval of one M block, optionally with terminal S clips."""
    if row["rname"] != expected_ref or row["rnext"] not in ("=", expected_ref):
        return None
    cigar = row["cigar"]
    ops = re.findall(r"(\d+)([MS])", cigar)
    if not ops or "".join(n + op for n, op in ops) != cigar:
        return None
    matches = [int(n) for n, op in ops if op == "M"]
    if len(matches) != 1 or matches[0] < 1:
        return None
    if sum(int(n) for n, _ in ops) != len(row["seq"]):
        return None
    if len(row["qual"]) != len(row["seq"]):
        return None
    start, length = int(row["pos"]) - 1, matches[0]
    if start < 0 or start + length > reference_length:
        return None
    return start, start + length


def compatible_targets(mates, refs, groups):
    if len(mates) != 2:
        return []
    source = mates[0]["rname"]
    if source not in groups or any(r["rname"] != source for r in mates):
        return []
    if {int(r["flag"]) for r in mates} not in _FLAGS:
        return []
    windows = [mapped_window(row, source, len(refs[source])) for row in mates]
    if any(window is None for window in windows):
        return []
    sequence = refs[source]
    return [target for target in groups[source]
            if all(sequence[a:b] == refs[target][a:b] for a, b in windows)]



def _valid_base_sites(mates, reference, minimum_quality=15):
    """Conservative source-allele Q15 coverage; reject variant/conflicted pairs."""
    calls = defaultdict(set)
    for row in mates:
        cigar = re.fullmatch(r"(?:(\d+)S)?([1-9]\d*)M(?:(\d+)S)?", row["cigar"])
        if cigar is None or len(row["qual"]) != len(row["seq"]):
            return None
        left_clip = int(cigar.group(1) or 0)
        aligned = int(cigar.group(2))
        if left_clip + aligned + int(cigar.group(3) or 0) != len(row["seq"]):
            return None
        start = int(row["pos"]) - 1
        if start < 0 or start + aligned > len(reference):
            return None
        for i in range(aligned):
            index = left_clip + i
            base = row["seq"][index].upper()
            if base in _DNA and ord(row["qual"][index]) - 33 >= minimum_quality:
                # A pair carrying any observed alternate source allele must
                # remain on its original hypothesis; neither protect the
                # source with it nor loan the variant to another hypothesis.
                if base != reference[start + i]:
                    return None
                calls[start + i].add(base)
    return tuple(calls)


def project_remap(remap_path, reference_path, output_path):
    """Allocate existing molecules once, never create synthetic read identities.

    The source retains at least 110 estimated reference-allele Q15 observations
    at each transferred base. Alternate-allele and conflicting pairs never move. Move only to a compatible hypothesis with low
    estimated depth; this is not a MiCall consensus-depth calculation.
    """
    remap_path = Path(remap_path)
    output_path = Path(output_path)
    if remap_path.resolve() == output_path.resolve():
        raise ValueError("remap input and output must be separate")
    refs = load_references(reference_path)
    groups = compatible_groups(refs)
    counts = Counter()
    fields = None
    with remap_path.open(newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        required = {"qname", "flag", "rname", "pos", "cigar", "rnext", "seq", "qual"}
        if not fields or not required <= set(fields):
            raise ValueError("missing SAM-like remap columns")
        counts.update(row["qname"] for row in reader)
    if not groups:
        return remap_path, {"groups": 0, "reassigned_pairs": 0}
    pending = {}
    pairs = []
    depth = {name: [0] * len(seq) for name, seq in refs.items()}
    with remap_path.open(newline="") as source:
        for row in csv.DictReader(source):
            name = row["qname"]
            if counts[name] != 2:
                continue
            first = pending.pop(name, None)
            if first is None:
                pending[name] = row
                continue
            mates = (first, row)
            ref = first["rname"]
            if ref not in refs or row["rname"] != ref:
                continue
            if {int(r["flag"]) for r in mates} not in _FLAGS:
                continue
            if any(mapped_window(r, ref, len(refs[ref])) is None for r in mates):
                continue
            sites = _valid_base_sites(mates, refs[ref])
            if not sites:
                continue
            for pos in sites:
                depth[ref][pos] += 1
            pairs.append((name, mates, ref, sites))
    transfers = {}
    moved = Counter()
    for name, mates, source, sites in pairs:
        options = compatible_targets(mates, refs, groups)
        if not options or any(depth[source][pos] <= _SOURCE_Q15_RESERVE for pos in sites):
            continue
        ranked = sorted(
            ((sum(max(0, _TARGET_Q15_GUIDE - depth[target][pos]) for pos in sites), target)
             for target in options),
            key=lambda value: (-value[0], value[1]),
        )
        if not ranked or ranked[0][0] == 0:
            continue
        target = ranked[0][1]
        transfers[name] = (source, target)
        moved[target] += 1
        for pos in sites:
            depth[source][pos] -= 1
            depth[target][pos] += 1
    if not transfers:
        return remap_path, {"groups": len(groups), "reassigned_pairs": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="w", newline="", dir=output_path.parent, prefix="ivanka-remap-",
            suffix=".csv", delete=False) as temp:
        intermediate = Path(temp.name)
        writer = csv.DictWriter(temp, fields, lineterminator="\n")
        try:
            writer.writeheader()
            with remap_path.open(newline="") as source:
                for row in csv.DictReader(source):
                    transfer = transfers.get(row["qname"])
                    if transfer is not None:
                        old, target = transfer
                        row["rname"] = target
                        if row["rnext"] == old:
                            row["rnext"] = target
                    writer.writerow(row)
        except BaseException:
            intermediate.unlink(missing_ok=True)
            raise
    os.replace(intermediate, output_path)
    return output_path, {
        "groups": len(groups), "reassigned_pairs": len(transfers),
        "reassigned_pairs_per_reference": dict(sorted(moved.items())),
        "output_read_records_added": 0,
        "read_identity_preserved": True,
    }
