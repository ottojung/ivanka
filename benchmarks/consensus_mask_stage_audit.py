"""Compare MiCall MAX consensus masking at the seed and final-output stages.

This is a diagnostic only. A seed sequence and a final consensus output may
have different coordinates and lengths: their mask counts are not subtracted
position by position. Exact flanking anchors can certify a local correspondence,
but do not establish read support or a biological haplotype.
"""
import argparse
import csv
import json
import re
from pathlib import Path

_COMPLEMENT = str.maketrans("ACGT", "TGCA")
_BASES = set("ACGT")


def reverse_complement(seq):
    return seq.translate(_COMPLEMENT)[::-1]


def max_rows(path, key, seed_only=False):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        needed = {"sample", key, "consensus-percent-cutoff", "sequence"}
        if seed_only:
            needed.add("region")
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: missing required columns {needed - set(reader.fieldnames or [])}")
        found = {}
        for row in reader:
            if row["consensus-percent-cutoff"] != "MAX":
                continue
            if seed_only and row.get("region"):
                continue
            identity = (row["sample"], row[key])
            if identity in found:
                raise ValueError(f"{path}: duplicate MAX row for {identity}")
            found[identity] = row["sequence"].upper()
        return found


def mask_runs(sequence):
    return [(match.start(), match.end()) for match in re.finditer("X+", sequence.upper())]


def exact_flank_correspondence(region, seed, start, end, anchor=31):
    """Return one orientation/offset only if both flanks map uniquely and exactly.

    A masked run is not evidence of missing reads. We require the same gap
    length, unambiguous ACGT flanks, and unambiguous ACGT seed interior.
    """
    if anchor < 1:
        raise ValueError("anchor must be positive")
    if start < anchor or end + anchor > len(region):
        return None
    left, right = region[start-anchor:start], region[end:end+anchor]
    if not set(left+right).issubset(_BASES):
        return None
    gap = end-start
    matches = []
    for strand, oriented in (("+", seed), ("-", reverse_complement(seed))):
        cursor = 0
        while True:
            pos = oriented.find(left, cursor)
            if pos == -1:
                break
            interior = oriented[pos+anchor:pos+anchor+gap]
            right_at = oriented[pos+anchor+gap:pos+2*anchor+gap]
            if len(interior) == gap and set(interior).issubset(_BASES) and right_at == right:
                matches.append((strand, pos))
            cursor = pos+1
    return matches[0] if len(matches) == 1 else None


def audit(region_rows, seed_rows, anchor=31):
    if anchor < 1:
        raise ValueError("anchor must be positive")
    output = []
    for (sample, region), sequence in sorted(region_rows.items()):
        seed = seed_rows.get((sample, region))
        runs = mask_runs(sequence)
        bridged = []
        if seed is not None:
            for start, end in runs:
                hit = exact_flank_correspondence(sequence, seed, start, end, anchor)
                if hit is not None:
                    bridged.append({"region_start": start, "length": end-start,
                                    "seed_strand": hit[0], "seed_flank_start": hit[1]})
        output.append({
            "sample": sample, "region": region,
            "final_region_length": len(sequence),
            "final_masked_bases": sum(end-start for start, end in runs),
            "final_mask_runs": len(runs),
            "longest_final_mask_run": max((end-start for start, end in runs), default=0),
            "matching_seed_max_row": seed is not None,
            "seed_length": len(seed) if seed is not None else None,
            "seed_masked_bases": sum(end-start for start, end in mask_runs(seed)) if seed is not None else None,
            "uniquely_exact_flank_bridged_runs": len(bridged),
            "uniquely_exact_flank_bridged_bases": sum(item["length"] for item in bridged),
            "exact_flank_bridges": bridged,
        })
    return {"coordinate_warning": "Seed and final consensus may have different coordinate systems; masks are not directly aligned. Exact flank bridges are not read support.",
            "anchor": anchor, "regions": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conseq_csv", type=Path)
    parser.add_argument("conseq_all_csv", type=Path)
    parser.add_argument("--anchor", type=int, default=31)
    args = parser.parse_args()
    result = audit(max_rows(args.conseq_csv, "region"),
                   max_rows(args.conseq_all_csv, "seed", seed_only=True), args.anchor)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
