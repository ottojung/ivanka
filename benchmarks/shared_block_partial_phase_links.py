"""Conservative partial-block / phase-SNP direct paired-read linkage audit.

A read pair must observe every base of a contiguous edge segment AND the
phase SNP. Never infer the remainder of a masked block or long-range phase.
"""
from collections import defaultdict
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

from shared_block_phase_links import discover_markers
from shared_block_consensus_candidate import _pair_signature, _strict_pair, canonical_base
from shared_locus_remap_coverage import sam_observations


def audit_partial_links(masked, references, rows, anchor=31, radius=600,
                        minimum_quality=15, lengths=(1, 4, 8, 16)):
    allele, loci, markers = discover_markers(masked, references, anchor, radius)
    requested = sorted(set(k for k in (*lengths, len(allele))
                           if 1 <= k <= len(allele)))
    coords = {name: dict(v) for name, v in loci.items()}
    for j, marker in enumerate(markers):
        for name, (pos, base) in marker["coords"].items():
            coords[name][pos] = (len(allele) + j, base)
    groups = defaultdict(list)
    for row in rows:
        groups[row["qname"]].append(row)
    records = [defaultdict(list) for _ in markers]
    by_signature = [defaultdict(lambda: defaultdict(set)) for _ in markers]
    for qname, pair in groups.items():
        if not _strict_pair(pair) or pair[0]["rname"] not in coords:
            continue
        name = pair[0]["rname"]
        observed = defaultdict(set)
        for row in pair:
            for site, base, _, expected in sam_observations(
                    row, coords[name], minimum_quality):
                canonical = (allele[site] if site < len(allele)
                             else markers[site-len(allele)]["alleles"][name])
                observed[site].add(canonical_base(base, expected, canonical))
        signature = _pair_signature(pair)
        for j, marker in enumerate(markers):
            marker_bases = observed[len(allele) + j]
            # For downstream markers require an observed block suffix; for
            # upstream markers require a prefix. No skipped bases are filled.
            indices = (range(len(allele)-1, -1, -1)
                       if marker["offset"] >= len(allele)
                       else range(len(allele)))
            run = []
            for i in indices:
                if len(observed[i]) != 1:
                    break
                run.append(next(iter(observed[i])))
            for k in requested:
                witness = None
                if len(marker_bases) == 1 and len(run) >= k:
                    block_part = ("".join(reversed(run[:k]))
                                  if marker["offset"] >= len(allele)
                                  else "".join(run[:k]))
                    witness = (block_part, next(iter(marker_bases)))
                    records[j][k].append((qname, signature, *witness))
                by_signature[j][k][signature].add(witness)
    output = []
    for j, (marker, by_length) in enumerate(zip(markers, records)):
        report = {}
        for k in requested:
            witnesses = by_length[k]
            spectra = defaultdict(set)
            for qname, signature, part, base in witnesses:
                spectra[(part, base)].add(qname)
            distinct = defaultdict(int)
            for signature, possibilities in by_signature[j][k].items():
                if len(possibilities) == 1 and None not in possibilities:
                    distinct[next(iter(possibilities))] += 1
            report[str(k)] = {
                "read_pair_ids": len({x[0] for x in witnesses}),
                "distinct_pair_sequences": sum(distinct.values()),
                "observed_linkages": [
                    {"block_edge_allele": part, "marker_base": base,
                     "read_pair_ids": len(qnames),
                     "distinct_pair_sequences": distinct[(part, base)]}
                    for (part, base), qnames in sorted(spectra.items())
                ],
            }
        output.append({"offset_from_block_start": marker["offset"],
                       "reference_marker_alleles": marker["alleles"],
                       "linkage_by_observed_edge_length": report})
    return {"shared_block_length": len(allele), "marker_anchor": anchor,
            "marker_search_radius": radius, "markers": output,
            "caveat": "Only directly observed contiguous block edges and SNPs "
                      "are linked. No full-block or haplotype phase is imputed."}


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
    args = parser.parse_args()
    with args.final_conseq_csv.open() as f:
        finals = [r for r in csv.DictReader(f)
                  if r["region"] == args.region and r["q-cutoff"] == "15"
                  and r["consensus-percent-cutoff"] == "MAX"]
    if len(finals) != 1:
        parser.error("Expected exactly one Q15 MAX final region")
    seq = finals[0]["sequence"]
    if (args.mask_start < 0 or args.mask_end <= args.mask_start or
            seq[args.mask_start:args.mask_end] !=
            "x" * (args.mask_end-args.mask_start)):
        parser.error("Mask interval must be an exact lowercase-x run")
    with args.remap_conseq_csv.open() as f:
        all_refs = {r["region"]: r["sequence"].upper() for r in csv.DictReader(f)}
    if len(set(args.reference)) != len(args.reference):
        parser.error("Duplicate reference")
    refs = {n: all_refs[n] for n in args.reference}
    with args.remap_sam_csv.open() as f:
        report = audit_partial_links(
            SimpleNamespace(sequence=seq, start=args.mask_start, end=args.mask_end),
            refs, csv.DictReader(f), args.anchor, args.radius)
    report.update({"region": args.region, "mask_start": args.mask_start,
                   "mask_end": args.mask_end})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
