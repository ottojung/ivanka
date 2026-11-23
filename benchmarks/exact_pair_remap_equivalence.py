"""CPU-only experiment: lift only exact, uniquely placed paired templates.

No remap/consensus files are written. Shared qnames are NOT independent
molecules; this measures read-pair compatibility, not haplotype assignment.
Never append these alternative alignments to MiCall remap.csv: its
matchmaker pairs by qname alone and its remap path ignores SAM MAPQ.
"""
import re
from collections import Counter, defaultdict

MATCH = re.compile(r"[1-9][0-9]*M\Z")
RC = str.maketrans("ACGT", "TGCA")
INVALID_FLAGS = 0x4 | 0x8 | 0x100 | 0x800


def reverse_complement(seq):
    return seq.translate(RC)[::-1]


def unique_placement(reference, template):
    """Return (zero-based start, reversed), rejecting all repeat ambiguity."""
    hits = []
    for reversed_strand, probe in ((False, template),
                                   (True, reverse_complement(template))):
        start = reference.find(probe)
        if start >= 0:
            if reference.find(probe, start + 1) >= 0:
                return None
            hits.append((start, reversed_strand))
    return hits[0] if len(hits) == 1 else None


def _valid_pair(rows, references, maximum_span):
    if len(rows) != 2:
        return None
    first, second = sorted(rows, key=lambda r: int(r["flag"]) & 0x80)
    flags = [int(r["flag"]) for r in (first, second)]
    if any(f & INVALID_FLAGS or f & 3 != 3 for f in flags):
        return None
    if not (flags[0] & 0x40) or flags[0] & 0x80:
        return None
    if not (flags[1] & 0x80) or flags[1] & 0x40:
        return None
    if bool(flags[0] & 0x10) == bool(flags[1] & 0x10):
        return None
    if (bool(flags[0] & 0x20) != bool(flags[1] & 0x10)
            or bool(flags[1] & 0x20) != bool(flags[0] & 0x10)):
        return None
    if (first["pnext"] != second["pos"]
            or second["pnext"] != first["pos"]):
        return None
    source = first["rname"]
    if source != second["rname"] or source not in references:
        return None
    starts, ends = [], []
    for row in (first, second):
        seq, qual = row["seq"].upper(), row["qual"]
        if not MATCH.fullmatch(row["cigar"]) or len(seq) != len(qual):
            return None
        if len(seq) != int(row["cigar"][:-1]) or not seq:
            return None
        if set(seq) - set("ACGT"):
            return None
        if row["rnext"] not in ("=", source):
            return None
        start = int(row["pos"]) - 1
        if start < 0 or start + len(seq) > len(references[source]):
            return None
        # Template equivalence is insufficient if an observed mate carries
        # a variant relative to the source: that variant may encode phase.
        # Keep the original alignment; do not propagate it to other targets.
        if seq != references[source][start:start + len(seq)]:
            return None
        starts.append(start)
        ends.append(start + len(seq))
    left, right = min(starts), max(ends)
    if right > len(references[source]) or right-left > maximum_span:
        return None
    template = references[source][left:right]
    if set(template) - set("ACGT"):
        return None
    if unique_placement(references[source], template) != (left, False):
        return None
    return (first, second), source, left, template


def lift_pair(rows, references, destination, maximum_span=1000):
    """Return two SAM-shaped copies iff whole pair footprint maps uniquely.

    The entire reference template, including the unsequenced insert, must
    be identical; both observed mates must also exactly match their source. Reverse-strand copies are reverse-complemented and have
    flags, mate positions, and template length recomputed.
    """
    valid = _valid_pair(rows, references, maximum_span)
    if valid is None:
        return None
    pair, source, left, template = valid
    if destination == source or destination not in references:
        return None
    placement = unique_placement(references[destination], template)
    if placement is None:
        return None
    dst_start, reversed_strand = placement
    output = []
    for row in pair:
        seq = row["seq"].upper()
        offset = int(row["pos"]) - 1 - left
        start = (dst_start + len(template) - offset - len(seq)
                 if reversed_strand else dst_start + offset)
        flag = int(row["flag"])
        copied = dict(row, rname=destination, pos=str(start + 1),
                      mapq="0", rnext="=", flag=str(flag ^ 0x30
                                                     if reversed_strand else flag),
                      seq=reverse_complement(seq) if reversed_strand else seq,
                      qual=row["qual"][::-1] if reversed_strand else row["qual"])
        output.append(copied)
    a, b = output
    for row, mate in ((a, b), (b, a)):
        row["pnext"] = mate["pos"]
        leftmost = (int(row["pos"]), not bool(int(row["flag"]) & 0x40))
        other = (int(mate["pos"]), not bool(int(mate["flag"]) & 0x40))
        row["tlen"] = str((1 if leftmost < other else -1) * len(template))
    return output


def compatible_copies(references, rows, selected, maximum_span=1000):
    """Read-only candidate copies and rejection counts; never writes remap."""
    selected = tuple(selected)
    if len(set(selected)) != len(selected) or any(n not in references for n in selected):
        raise ValueError("References must be distinct and present")
    groups = defaultdict(list)
    for row in rows:
        groups[row["qname"]].append(row)
    copies, stats = [], Counter()
    for group in groups.values():
        if len(group) != 2:
            stats["nonunique_qname"] += 1
            continue
        source = group[0]["rname"]
        if source not in selected:
            continue
        if _valid_pair(group, references, maximum_span) is None:
            stats["ineligible_pair"] += 1
            continue
        stats["eligible_pair"] += 1
        for target in selected:
            if target == source:
                continue
            transferred = lift_pair(group, references, target, maximum_span)
            if transferred is None:
                stats["incompatible_target"] += 1
            else:
                copies.extend(transferred)
                stats["transferred_pair"] += 1
    return copies, dict(stats)


def pooled_site_calls(masked, references, rows, minimum_quality=15):
    """Observed (position, qname, allele), regardless of target allocation.

    An exact template lift may redistribute support but must never create
    a new distinct observed read-pair/base at the shared locus.
    """
    from shared_locus_remap_coverage import group_loci, sam_observations
    allele, loci = group_loci(masked, references)
    complement = str.maketrans("ACGT", "TGCA")
    calls = set()
    for row in rows:
        coords = loci.get(row["rname"])
        if coords is None:
            continue
        for pos, base, qname, expected in sam_observations(
                row, coords, minimum_quality):
            canonical = (base if expected == allele[pos]
                         else base.translate(complement))
            calls.add((pos, qname, canonical))
    return calls


def verified_source_references(stitched_rows, remap_rows, selected):
    """Resolve MiCall's REMAPPED names by exact sequence, never row number.

    MiCall can drop/reorder stitched inputs before naming remap references,
    so 13-HCV-1a may originate from stitched row 2, not row 13. To avoid
    inventing a connection, demand a UNIQUE full-length exact source sequence
    and a consistent reference/partial label. Changed consensuses fail closed.
    """
    by_sequence = defaultdict(list)
    for row in stitched_rows:
        by_sequence[row["contig"].upper()].append(row["ref"])
    remap = {}
    for row in remap_rows:
        name = row["region"]
        if name in remap:
            raise ValueError(f"Repeated remap reference {name}")
        remap[name] = row["sequence"].upper()
    verified = {}
    for name in selected:
        if name not in remap:
            raise ValueError(f"Missing remap reference {name}")
        sequence = remap[name]
        if not sequence or set(sequence) - set("ACGT"):
            raise ValueError(f"Ambiguous remap reference {name}")
        matches = by_sequence.get(sequence, ())
        if len(matches) != 1:
            raise ValueError(f"No unique exact stitched source for {name}")
        number, separator, suffix = name.partition("-")
        source_ref = matches[0]
        if not separator or not number.isdigit() or suffix not in (
                source_ref, source_ref + "-partial"):
            raise ValueError(f"Reference label does not match source {name}")
        verified[name] = sequence
    if len(set(verified.values())) != len(verified):
        raise ValueError("Multiple remap references share one source sequence")
    return verified


def main():
    """Audit a saved MiCall remap, never rewrite or patch it."""
    import argparse
    import csv
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from consensus_mask_stage_audit import mask_runs
    from shared_locus_remap_coverage import audit

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("stitched_contigs_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("remap_sam_csv", type=Path)
    parser.add_argument("--region", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--mask-length", type=int, required=True)
    parser.add_argument("--maximum-span", type=int, default=1000)
    args = parser.parse_args()
    if args.mask_length < 1 or args.maximum_span < 1:
        parser.error("Mask length and maximum span must be positive")
    if len(args.reference) < 2 or len(set(args.reference)) != len(args.reference):
        parser.error("Select at least two distinct remap references")

    with args.final_conseq_csv.open() as f:
        finals = [r for r in csv.DictReader(f)
                  if r["region"] == args.region and r["q-cutoff"] == "15"
                  and r["consensus-percent-cutoff"] == "MAX"]
    if len(finals) != 1:
        parser.error("Expected exactly one selected final MAX consensus")
    masks = [(s, e) for s, e in mask_runs(finals[0]["sequence"])
             if e-s == args.mask_length]
    if len(masks) != 1:
        parser.error("Mask length must select exactly one masked interval")
    with args.stitched_contigs_csv.open() as f:
        stitched_rows = list(csv.DictReader(f))
    with args.remap_conseq_csv.open() as f:
        remap_rows = list(csv.DictReader(f))
    selected = verified_source_references(stitched_rows, remap_rows,
                                          args.reference)
    # Only these exact-verified references are eligible for propagation.
    references = selected
    with args.remap_sam_csv.open() as f:
        rows = list(csv.DictReader(f))
    copies, stats = compatible_copies(references, rows, selected,
                                     args.maximum_span)
    if not {r["qname"] for r in copies}.issubset({r["qname"] for r in rows}):
        raise AssertionError("Candidate invented a read-pair ID")
    start, end = masks[0]
    masked = SimpleNamespace(sequence=finals[0]["sequence"],
                             start=start, end=end)
    baseline = audit(masked, selected, rows)
    candidate = audit(masked, selected, rows+copies)
    before = baseline["pooled_deduplicated"]["per_position"]
    after = candidate["pooled_deduplicated"]["per_position"]
    if before != after:
        raise AssertionError("Candidate changed distinct pooled read-pair support")
    observed = pooled_site_calls(masked, selected, rows)
    proposed = pooled_site_calls(masked, selected, rows+copies)
    if observed != proposed:
        raise AssertionError("Candidate created a distinct pooled allele observation")
    print(json.dumps({
        "region": args.region, "mask_start": start, "mask_length": end-start,
        "minimum_quality": 15, "observed_mates_must_match_source": True,
        "original_sam_rows": len(rows),
        "hypothetical_copy_rows": len(copies), "statistics": stats,
        "per_reference_min_before": {
            n: v["minimum"] for n, v in baseline["per_reference"].items()},
        "per_reference_min_after": {
            n: v["minimum"] for n, v in candidate["per_reference"].items()},
        "pooled_deduplicated_min_unchanged": min(before),
        "distinct_pooled_qname_allele_observations_unchanged": len(observed),
        "qualification": "NOT RUN: diagnostic only; no MiCall files modified",
        "caveat": "A qname is a read-pair ID, not an independent molecule. "
                  "Copies across contigs are alternative compatible mappings, "
                  "not independent observations or long-range phase evidence. "
                  "MiCall matches mates by qname alone and ignores MAPQ; "
                  "never append these hypothetical mappings to its remap CSV."
    }, indent=2))


if __name__ == "__main__":
    main()
