"""Conservative raw-read support for a seed allele hidden by a final MAX mask.

This is a diagnostic, not a consensus correction. Flanks unique within
a single final region identify a masked local sequence context. A read spanning
both flanks supports that local allele; if a seed has a unique exact bridge,
its allele can also be compared. Neither proves a complete seed haplotype. Read pairs are counted once; they are not necessarily distinct
original molecules.
"""
import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path

from consensus_mask_stage_audit import (
    exact_flank_correspondence, mask_runs, max_rows, reverse_complement,
)

_BASES = frozenset("ACGT")


def _open_fastq(path):
    path = Path(path)
    return gzip.open(path, "rt") if path.suffix == ".gz" else path.open("rt")


def _record(handle):
    header = handle.readline()
    if not header:
        return None
    seq, plus, quality = (handle.readline() for _ in range(3))
    if not seq or not plus or not quality:
        raise ValueError("truncated FASTQ record")
    seq = seq.strip().upper()
    if not header.startswith("@") or not plus.startswith("+"):
        raise ValueError("malformed FASTQ record")
    if len(seq) != len(quality.rstrip("\r\n")):
        raise ValueError("FASTQ sequence/quality length mismatch")
    name = header[1:].split()[0].removesuffix("/1").removesuffix("/2")
    return name, seq


def fastq_pairs(r1, r2, limit=5000):
    if limit < 1:
        raise ValueError("limit must be positive")
    with ExitStack() as stack:
        first = stack.enter_context(_open_fastq(r1))
        second = stack.enter_context(_open_fastq(r2))
        for _ in range(limit):
            a, b = _record(first), _record(second)
            if a is None and b is None:
                break
            if a is None or b is None:
                raise ValueError("FASTQ mates have unequal record counts")
            if a[0] != b[0]:
                raise ValueError("FASTQ mate identifiers differ")
            yield a[1], b[1]


def spanning_alleles(read, left, right, gap):
    """All ACGT alleles with both exact flanks on one read, either strand."""
    alleles = set()
    if len(read) < len(left) + gap + len(right):
        return alleles
    for oriented in (read, reverse_complement(read)):
        start = 0
        while True:
            pos = oriented.find(left, start)
            if pos == -1:
                break
            interior_start = pos + len(left)
            interior_end = interior_start + gap
            if oriented[interior_end:interior_end + len(right)] == right:
                allele = oriented[interior_start:interior_end]
                if set(allele).issubset(_BASES):
                    alleles.add(allele)
            start = pos + 1
    return alleles


def audit_mask_read_support(region_rows, seed_rows, read_pairs, anchor=31):
    if anchor < 1:
        raise ValueError("anchor must be positive")
    reports = []
    for (sample, region), sequence in sorted(region_rows.items()):
        seed = seed_rows.get((sample, region))
        for start, end in mask_runs(sequence):
            left, right = sequence[start-anchor:start], sequence[end:end+anchor]
            region_unique_flanks = (
                len(left) == anchor and len(right) == anchor
                and set(left + right).issubset(_BASES)
                and sequence.count(left) == 1 and sequence.count(right) == 1
            )
            item = {"sample": sample, "region": region, "mask_start": start,
                    "mask_end": end, "mask_length": end - start,
                    "region_unique_flanks": region_unique_flanks,
                    "unique_seed_flank_bridge": False,
                    "exact_bridge_pairs": 0, "ambiguous_pairs": 0,
                    "observed_alleles": {}}
            if region_unique_flanks:
                item["_left"], item["_right"] = left, right
                if seed is not None:
                    hit = exact_flank_correspondence(sequence, seed, start, end, anchor)
                    if hit is not None:
                        strand, pos = hit
                        oriented_seed = seed if strand == "+" else reverse_complement(seed)
                        allele = oriented_seed[pos + anchor:pos + anchor + end - start]
                        item.update(unique_seed_flank_bridge=True, seed_strand=strand,
                                    seed_allele=allele, seed_support_pairs=0,
                                    alternative_support_pairs=0, alternative_alleles={})
            reports.append(item)

    pairs_seen = 0
    for reads in read_pairs:
        pairs_seen += 1
        for item in reports:
            if not item["region_unique_flanks"]:
                continue
            alleles = set()
            for read in reads:
                alleles.update(spanning_alleles(
                    read.upper(), item["_left"], item["_right"], item["mask_length"]))
            if len(alleles) > 1:
                item["ambiguous_pairs"] += 1
            elif alleles:
                item["exact_bridge_pairs"] += 1
                allele = next(iter(alleles))
                observed = item["observed_alleles"]
                observed[allele] = observed.get(allele, 0) + 1
                if item["unique_seed_flank_bridge"]:
                    if allele == item["seed_allele"]:
                        item["seed_support_pairs"] += 1
                    else:
                        item["alternative_support_pairs"] += 1
                        alternatives = item["alternative_alleles"]
                        alternatives[allele] = alternatives.get(allele, 0) + 1

    for item in reports:
        item.pop("_left", None)
        item.pop("_right", None)
        item["observed_alleles"] = dict(sorted(
            item["observed_alleles"].items(), key=lambda x: (-x[1], x[0])))
        if item["unique_seed_flank_bridge"]:
            item["alternative_alleles"] = dict(sorted(
                item["alternative_alleles"].items(), key=lambda x: (-x[1], x[0])))
    return {
        "processed_read_pairs": pairs_seen,
        "anchor": anchor,
        "interpretation": ("Counts require flanks unique within a final region and exact on one read; flanks may recur in other contigs; "
                           "they do not prove a complete phased haplotype or independent molecules."),
        "mask_runs": reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conseq_csv", type=Path)
    parser.add_argument("conseq_all_csv", type=Path)
    parser.add_argument("fastq_r1", type=Path)
    parser.add_argument("fastq_r2", type=Path)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--region")
    parser.add_argument("--max-pairs", type=int, default=5000)
    parser.add_argument("--anchor", type=int, default=31)
    args = parser.parse_args()
    regions = {key: seq for key, seq in max_rows(args.conseq_csv, "region").items()
               if key[0] == args.sample and (args.region is None or key[1] == args.region)}
    if not regions:
        parser.error("no final MAX region rows match the requested sample/region")
    seeds = max_rows(args.conseq_all_csv, "seed", seed_only=True)
    result = audit_mask_read_support(
        regions, seeds, fastq_pairs(args.fastq_r1, args.fastq_r2, args.max_pairs), args.anchor)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
