"""Read-only shared-locus support audit deduplicated by observed paired sequences.

Identical read-pair strings are NOT proven PCR duplicates, and different strings
are NOT proven independent molecules. No remap/consensus files are modified.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from consensus_mask_stage_audit import mask_runs, max_rows
from shared_locus_remap_coverage import group_loci, sam_observations

_BASES = set("ACGT")
_COMP = str.maketrans("ACGT", "TGCA")
_BAD_FLAGS = 0x4 | 0x8 | 0x100 | 0x800


def reverse_complement(sequence):
    return sequence.translate(_COMP)[::-1]


def paired_sequence_signature(rows):
    """Canonical read1/read2 strings; reject incomplete SAM pairs.

    MiCall remap may emit the same TLEN sign for both mates, so TLEN
    is not a safe validity test for observed paired-sequence identity.
    """
    if len(rows) != 2:
        return None
    flags = [int(row["flag"]) for row in rows]
    if any(flag & _BAD_FLAGS or flag & 3 != 3 for flag in flags):
        return None
    first = [row for row, flag in zip(rows, flags) if flag & 0x40]
    second = [row for row, flag in zip(rows, flags) if flag & 0x80]
    if len(first) != 1 or len(second) != 1:
        return None
    a, b = first[0], second[0]
    fa, fb = int(a["flag"]), int(b["flag"])
    if fa & 0x80 or fb & 0x40:
        return None
    if bool(fa & 0x10) == bool(fb & 0x10):
        return None
    if bool(fa & 0x20) != bool(fb & 0x10):
        return None
    if bool(fb & 0x20) != bool(fa & 0x10):
        return None
    if a["rname"] != b["rname"] or a["rnext"] not in ("=", a["rname"]):
        return None
    if b["rnext"] not in ("=", b["rname"]):
        return None
    try:
        if int(a["pos"]) < 1 or int(b["pos"]) < 1:
            return None
        if int(a["pnext"]) != int(b["pos"]) or int(b["pnext"]) != int(a["pos"]):
            return None
    except (ValueError, KeyError):
        return None
    strings = []
    for row, flag in ((a, fa), (b, fb)):
        seq = row["seq"].upper()
        if not seq or set(seq) - _BASES or len(seq) != len(row["qual"]):
            return None
        strings.append(reverse_complement(seq) if flag & 0x10 else seq)
    return tuple(strings)


def audit(masked, references, rows, minimum_quality=15):
    """Compare qname and exact paired-sequence diversity at shared loci."""
    if minimum_quality < 0:
        raise ValueError("Minimum quality must be nonnegative")
    allele, loci = group_loci(masked, references)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["qname"]].append(row)
    signatures = {}
    calls = [defaultdict(set) for _ in allele]
    invalid = 0
    for qname, pair in grouped.items():
        if not qname or not any(r["rname"] in loci for r in pair):
            continue
        signature = paired_sequence_signature(pair)
        if signature is None or pair[0]["rname"] not in loci:
            invalid += 1
            continue
        observed = []
        try:
            for row in pair:
                for i, base, _, expected in sam_observations(
                        row, loci[row["rname"]], minimum_quality):
                    canonical = (base if expected == allele[i]
                                 else base.translate(_COMP))
                    observed.append((i, canonical))
        except (ValueError, KeyError):
            invalid += 1
            continue
        signatures[qname] = signature
        for i, base in observed:
            calls[i][qname].add(base)
    per_position = []
    for i, site_calls in enumerate(calls):
        signature_alleles = defaultdict(set)
        for qname, bases in site_calls.items():
            signature_alleles[signatures[qname]].update(bases)
        unambiguous = {
            q: next(iter(bases)) for q, bases in site_calls.items()
            if len(bases) == 1 and next(iter(bases)) in _BASES
        }
        per_allele = {}
        for base in "ACGT":
            qnames = sum(value == base for value in unambiguous.values())
            strings = sum(bases == {base} for bases in signature_alleles.values())
            per_allele[base] = {
                "read_pair_ids": qnames,
                "distinct_paired_sequences": strings,
            }
        per_position.append({
            "index": i, "seed_allele": allele[i],
            "alleles": per_allele,
            "conflicted_read_pair_ids": len(site_calls)-len(unambiguous),
            "ambiguous_paired_sequences": sum(
                len(bases) != 1 or not bases.issubset(_BASES)
                for bases in signature_alleles.values()),
        })
    return {
        "masked_bases": len(allele),
        "eligible_read_pairs": len(signatures),
        "distinct_paired_sequences_across_pairs": len(set(signatures.values())),
        "invalid_or_nonunique_read_pairs": invalid,
        "minimum_seed_read_pair_ids": min(
            p["alleles"][p["seed_allele"]]["read_pair_ids"]
            for p in per_position),
        "minimum_seed_distinct_paired_sequences": min(
            p["alleles"][p["seed_allele"]]["distinct_paired_sequences"]
            for p in per_position),
        "per_position": per_position,
        "caveat": ("Paired-sequence identity is only an observable diversity "
                   "proxy, not a molecule or haplotype identity. Counts are "
                   "across targets, not independent coverage for each target."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("remap_sam_csv", type=Path)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--mask-length", type=int, required=True)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--per-position", action="store_true")
    args = parser.parse_args()
    if args.mask_length < 1 or len(args.reference) < 2:
        parser.error("Select a positive mask length and at least two references")
    if len(set(args.reference)) != len(args.reference):
        parser.error("Reference names must be distinct")
    sequence = max_rows(args.final_conseq_csv, "region").get(
        (args.sample, args.region))
    if sequence is None:
        parser.error("No matching final MAX consensus")
    runs = [(start, end) for start, end in mask_runs(sequence)
            if end-start == args.mask_length]
    if len(runs) != 1:
        parser.error("Mask length must identify exactly one run")
    with args.remap_conseq_csv.open(newline="") as handle:
        remap = list(csv.DictReader(handle))
    if len({r["region"] for r in remap}) != len(remap):
        parser.error("Duplicate remap reference")
    seeds = {r["region"]: r["sequence"].upper() for r in remap}
    if any(name not in seeds for name in args.reference):
        parser.error("Missing selected remap reference")
    selected = {name: seeds[name] for name in args.reference}
    start, end = runs[0]
    masked = SimpleNamespace(sequence=sequence, start=start, end=end)
    with args.remap_sam_csv.open(newline="") as handle:
        result = audit(masked, selected, csv.DictReader(handle), args.min_phred)
    result.update({"sample": args.sample, "region": args.region,
                   "mask_start": start})
    if not args.per_position:
        result["first_position"] = result["per_position"][0]
        del result["per_position"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
