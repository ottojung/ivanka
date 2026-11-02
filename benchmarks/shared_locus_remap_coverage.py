"""Read-only, deduplicated remap-depth audit for exact shared masked loci.

Distinct SAM qnames are read-pair identifiers, NOT independent original
molecules. This script never changes remapping, coverage thresholds, or calls.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from consensus_mask_stage_audit import mask_runs, max_rows
from shared_mask_locus_audit import exact_hits

CIGAR = re.compile(r"(\d+)([MIDNSHP=X])")
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def group_loci(masked, references, anchor=31):
    """Require a unique, identical flanked allele on every named seed."""
    if len(references) < 2 or anchor < 1:
        raise ValueError("Select at least two references and a positive anchor")
    start, end = masked.start, masked.end
    if start < anchor or end + anchor > len(masked.sequence):
        raise ValueError("Insufficient unmasked flanks")
    left = masked.sequence[start-anchor:start]
    right = masked.sequence[end:end+anchor]
    if set(left+right) - set("ACGT"):
        raise ValueError("Flanks are not fully resolved")
    allele, loci = None, {}
    for name, seq in references.items():
        hits = exact_hits(seq.upper(), left, right, end-start)
        if len(hits) != 1:
            raise ValueError(f"{name}: expected one exact locus, got {len(hits)}")
        strand, pos, value = hits[0]
        if allele is not None and value != allele:
            raise ValueError(f"{name}: conflicting allele across shared locus")
        allele = value
        coords = {}
        for i, base in enumerate(value):
            if strand == "+":
                coord, target = pos + anchor + i, base
            else:
                coord = len(seq) - 1 - (pos + anchor + i)
                target = base.translate(COMPLEMENT)
            coords[coord] = (i, target)
        loci[name] = coords
    return allele, loci


def sam_observations(row, coords, minimum_quality=15):
    """Yield (canonical mask position, base, qname) from quality-filtered SAM."""
    if int(row["flag"]) & 4 or row["cigar"] == "*":
        return
    seq, qual = row["seq"].upper(), row["qual"]
    if len(seq) != len(qual) or not row["qname"]:
        raise ValueError("Malformed sequence, quality, or read identifier")
    cigar = row["cigar"]
    parts = CIGAR.findall(cigar)
    if not parts or "".join(n + op for n, op in parts) != cigar:
        raise ValueError(f"Malformed CIGAR {cigar!r}")
    ref, query = int(row["pos"])-1, 0
    for n_text, op in parts:
        n = int(n_text)
        if n < 1:
            raise ValueError("Zero-length CIGAR operation")
        if op in "M=X":
            for coord in range(ref, ref+n):
                site = coords.get(coord)
                if site is None:
                    continue
                j = query + coord-ref
                if j < len(seq) and ord(qual[j])-33 >= minimum_quality:
                    yield site[0], seq[j], row["qname"], site[1]
            ref += n
            query += n
        elif op in "DN":
            ref += n
        elif op in "IS":
            query += n
    if query != len(seq):
        raise ValueError("CIGAR does not consume all read bases")


def audit(masked, references, sam_rows, anchor=31, minimum_quality=15,
          required_depth=100):
    """Count one read-pair ID per base across all compatible remapping targets."""
    if minimum_quality < 0 or required_depth < 1:
        raise ValueError("Invalid quality or depth threshold")
    allele, loci = group_loci(masked, references, anchor)
    matched = {ref: [set() for _ in allele] for ref in loci}
    conflicted = {ref: [set() for _ in allele] for ref in loci}
    for row in sam_rows:
        name = row["rname"]
        if name not in loci:
            continue
        for i, nuc, qname, expected in sam_observations(row, loci[name], minimum_quality):
            (matched if nuc == expected else conflicted)[name][i].add(qname)
    per_reference = {}
    for name in loci:
        counts = [len(matched[name][i]-conflicted[name][i]) for i in range(len(allele))]
        per_reference[name] = {"minimum": min(counts), "maximum": max(counts),
                               "mean": round(sum(counts)/len(counts), 2)}
    pooled = []
    discordant = []
    for i in range(len(allele)):
        good = set().union(*(matched[name][i] for name in loci))
        bad = set().union(*(conflicted[name][i] for name in loci))
        pooled.append(len(good-bad))
        discordant.append(len(bad))
    return {
        "reference_names": sorted(loci), "masked_bases": len(allele),
        "shared_allele_sha256": hashlib.sha256(allele.encode()).hexdigest(),
        "min_phred": minimum_quality, "required_depth": required_depth,
        "per_reference": per_reference,
        "pooled_deduplicated": {"minimum": min(pooled), "maximum": max(pooled),
                                "mean": round(sum(pooled)/len(pooled), 2),
                                "per_position": pooled,
                                "positions_meeting_depth": sum(n>=required_depth for n in pooled)},
        "discordant_pair_ids_per_position": discordant,
        "interpretation": ("Pooled qname counts are upper bounds on independent "
            "molecules; this is a read-only diagnostic, not permission to fill "
            "masked bases or change MiCall coverage/PSI gates."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("remap_sam_csv", type=Path)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--anchor", type=int, default=31)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--required-depth", type=int, default=100)
    args = parser.parse_args()
    rows = max_rows(args.final_conseq_csv, "region")
    sequence = rows.get((args.sample, args.region))
    if sequence is None:
        parser.error("Requested sample/region has no final MAX consensus")
    seeds = {row["region"]: row["sequence"].upper()
             for row in csv.DictReader(args.remap_conseq_csv.open())}
    selected = {}
    for name in args.reference:
        if name not in seeds or name in selected:
            parser.error(f"Missing or repeated reference {name}")
        selected[name] = seeds[name]
    results = []
    for start, end in mask_runs(sequence):
        from types import SimpleNamespace
        masked = SimpleNamespace(sequence=sequence, start=start, end=end)
        with args.remap_sam_csv.open() as fh:
            result = audit(masked, selected, csv.DictReader(fh),
                           args.anchor, args.min_phred, args.required_depth)
        result.update({"sample": args.sample, "region": args.region,
                       "mask_start": start, "mask_length": end-start})
        results.append(result)
    print(json.dumps({"mask_runs": results}, indent=2))


if __name__ == "__main__":
    main()
