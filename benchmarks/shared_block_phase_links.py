"""Read-only direct paired-read linkage of a shared block to phase markers.

A marker must be a uniquely flanked, aligned SNP among the actual remap
contigs. A linkage requires the SAME strict read pair to observe every base
of the block and the marker; unsequenced inserts never count as observations.
No mapping, MiCall calls, coverage thresholds, or haplotypes are changed.
"""
from collections import defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from shared_block_consensus_candidate import (
    _pair_signature, _strict_pair, canonical_base, COMPLEMENT,
)
from shared_locus_remap_coverage import group_loci, sam_observations

BASES = frozenset("ACGT")


def discover_markers(masked, references, anchor=31, radius=600):
    """Find only single-base variants with identical unique flanks in all refs."""
    if anchor < 1 or radius < 1:
        raise ValueError("Invalid marker search window")
    allele, loci = group_loci(masked, references, anchor)
    if len(allele) < 2:
        raise ValueError("Need two shared bases to orient references")
    oriented = {}
    for name in sorted(loci):
        index = {site: coord for coord, (site, _) in loci[name].items()}
        reverse = index[1] < index[0]
        seq = references[name].upper()
        if reverse:
            seq = seq.translate(COMPLEMENT)[::-1]
        start = len(seq) - 1 - index[0] if reverse else index[0]
        if seq[start:start + len(allele)] != allele:
            raise ValueError("Shared locus orientation mismatch")
        oriented[name] = (seq, start, reverse)
    markers = []
    for offset in range(-radius, len(allele) + radius):
        if 0 <= offset < len(allele):
            continue
        flanks, bases = set(), {}
        for name, (seq, start, _) in oriented.items():
            p = start + offset
            if p < anchor or p + anchor >= len(seq):
                break
            left, base, right = seq[p-anchor:p], seq[p], seq[p+1:p+1+anchor]
            if set(left + base + right) - BASES:
                break
            if seq.count(left + base + right) != 1:
                break
            flanks.add((left, right))
            bases[name] = base
        if len(bases) != len(oriented) or len(flanks) != 1:
            continue
        if len(set(bases.values())) < 2:
            continue
        coords = {}
        for name, (seq, start, reverse) in oriented.items():
            p = start + offset
            native = len(seq) - 1 - p if reverse else p
            original_base = (bases[name].translate(COMPLEMENT)
                             if reverse else bases[name])
            coords[name] = (native, original_base)
        markers.append({"offset": offset, "alleles": bases, "coords": coords})
    return allele, loci, markers


def audit_links(masked, references, sam_rows, anchor=31, radius=600,
                minimum_quality=15):
    """Report direct block/marker co-observations; no inferred phase assignment."""
    allele, loci, markers = discover_markers(masked, references, anchor, radius)
    coords = {name: dict(items) for name, items in loci.items()}
    for i, marker in enumerate(markers):
        for name, (pos, base) in marker["coords"].items():
            coords[name][pos] = (len(allele) + i, base)
    by_qname = defaultdict(list)
    for row in sam_rows:
        by_qname[row["qname"]].append(row)
    complete_block_pair_ids = set()
    marker_observed_pair_ids = [set() for _ in markers]
    by_marker = [defaultdict(set) for _ in markers]
    by_signature = [defaultdict(set) for _ in markers]
    for qname, rows in by_qname.items():
        if not _strict_pair(rows) or rows[0]["rname"] not in coords:
            continue
        name = rows[0]["rname"]
        signature = _pair_signature(rows)
        observed = defaultdict(set)
        for row in rows:
            for site, base, _, expected in sam_observations(
                    row, coords[name], minimum_quality):
                canonical = (allele[site] if site < len(allele)
                             else markers[site - len(allele)]["alleles"][name])
                observed[site].add(canonical_base(base, expected, canonical))
        complete = all(len(observed[i]) == 1 for i in range(len(allele)))
        block = ("".join(next(iter(observed[i])) for i in range(len(allele)))
                 if complete else None)
        if complete:
            complete_block_pair_ids.add(qname)
        for i in range(len(markers)):
            marker_bases = observed[len(allele) + i]
            if len(marker_bases) == 1:
                marker_observed_pair_ids[i].add(qname)
            witness = ((block, next(iter(marker_bases)))
                       if block is not None and len(marker_bases) == 1 else None)
            by_signature[i][signature].add(witness)
            if witness is not None:
                by_marker[i][witness].add(qname)
    reports = []
    for i, marker in enumerate(markers):
        distinct = defaultdict(int)
        for witnesses in by_signature[i].values():
            if len(witnesses) == 1 and None not in witnesses:
                distinct[next(iter(witnesses))] += 1
        spectrum = []
        for witness, qnames in sorted(by_marker[i].items()):
            spectrum.append({
                "block_allele": witness[0], "marker_base": witness[1],
                "read_pair_ids": len(qnames),
                "distinct_pair_sequences": distinct[witness],
            })
        reports.append({
            "offset_from_block_start": marker["offset"],
            "reference_marker_alleles": marker["alleles"],
            "marker_observed_pair_ids": len(marker_observed_pair_ids[i]),
            "linked_read_pair_ids": sum(len(v) for v in by_marker[i].values()),
            "linked_distinct_pair_sequences": sum(distinct.values()),
            "observed_linkages": spectrum,
        })
    return {
        "shared_block_length": len(allele),
        "complete_block_pair_ids": len(complete_block_pair_ids),
        "shared_block_sha256": hashlib.sha256(allele.encode()).hexdigest(),
        "marker_anchor": anchor,
        "marker_search_radius": radius,
        "markers": reports,
        "interpretation": "Direct two-mate observed block-to-SNP linkage only; "
                          "not molecule independence or whole-haplotype phase.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("remap_sam_csv", type=Path)
    parser.add_argument("--region", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--mask-start", type=int, required=True)
    parser.add_argument("--mask-end", type=int, required=True)
    parser.add_argument("--anchor", type=int, default=31)
    parser.add_argument("--radius", type=int, default=600)
    parser.add_argument("--min-phred", type=int, default=15)
    args = parser.parse_args()
    with args.final_conseq_csv.open() as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["region"] == args.region and r["q-cutoff"] == "15"
                and r["consensus-percent-cutoff"] == "MAX"]
    if len(rows) != 1:
        parser.error("Expected exactly one Q15 MAX final region")
    seq = rows[0]["sequence"]
    if (args.mask_start < 0 or args.mask_end <= args.mask_start
            or seq[args.mask_start:args.mask_end] !=
            "x" * (args.mask_end - args.mask_start)):
        parser.error("Selected interval is not an exact lowercase-x mask")
    masked = SimpleNamespace(sequence=seq, start=args.mask_start,
                             end=args.mask_end)
    with args.remap_conseq_csv.open() as fh:
        seeds = {r["region"]: r["sequence"].upper()
                 for r in csv.DictReader(fh)}
    if len(set(args.reference)) != len(args.reference):
        parser.error("Duplicate remap reference")
    try:
        refs = {name: seeds[name] for name in args.reference}
    except KeyError as exc:
        parser.error(f"Missing remap reference {exc}")
    with args.remap_sam_csv.open() as fh:
        report = audit_links(masked, refs, csv.DictReader(fh),
                             args.anchor, args.radius, args.min_phred)
    report.update({"region": args.region, "mask_start": args.mask_start,
                   "mask_end": args.mask_end})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
