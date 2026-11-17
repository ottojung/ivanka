"""Create privacy-preserving per-cycle Phred quantiles from real paired FASTQs.

Only aggregate quality counts leave this process; no read bases, IDs or paths.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from .read_model import READ_LENGTH

RANKS = [1, 3, 5, 7, 9, 11, 13, 15]


def build(root, *, expected=198, reads_per_file=128):
    bins = [[Counter() for _ in range(READ_LENGTH)] for _ in range(2)]
    counts, files = [0, 0], [0, 0]
    for mate in (1, 2):
        paths = sorted(Path(root).glob(f"*/*_R{mate}_001.fastq.gz"))
        if len(paths) != expected:
            raise ValueError("wrong number of frozen source FASTQ files")
        for path in paths:
            files[mate - 1] += 1
            with gzip.open(path, "rt") as handle:
                for _ in range(reads_per_file):
                    try:
                        next(handle)
                        next(handle)
                        next(handle)
                        qual = next(handle).strip()
                    except StopIteration:
                        break
                    if len(qual) < READ_LENGTH:
                        continue
                    counts[mate - 1] += 1
                    for index, symbol in enumerate(qual[:READ_LENGTH]):
                        q = ord(symbol) - 33
                        if not 0 <= q <= 41:
                            raise ValueError("unsupported source Phred encoding")
                        bins[mate - 1][index][q] += 1
    quantiles = []
    for mate in bins:
        positions = []
        for tally in mate:
            total = sum(tally.values())
            if not total:
                raise ValueError("source quality cycle not observed")
            values = []
            for rank in RANKS:
                threshold = (total * rank + 15) // 16
                position = 0
                for q, n in sorted(tally.items()):
                    position += n
                    if position >= threshold:
                        values.append(q)
                        break
            positions.append(values)
        quantiles.append(positions)
    return {
        "schema": "ivanka.synthetic.quality_profile.v1",
        "description": ("Per-cycle Phred quantiles from paired FASTQ qualities "
                        "only; no read sequences, identifiers or patient-level records"),
        "read_length": READ_LENGTH,
        "sources": "frozen 198 physical MiCall benchmark libraries",
        "files_per_mate": files,
        "sampled_reads_per_file_max": reads_per_file,
        "sampled_read_counts": counts,
        "quantile_numerators": RANKS,
        "quantile_denominator": 16,
        "cycle_quantiles": quantiles,
        "caveat": ("Quality marginals only; does not calibrate read-sequence error, "
                   "PCR, insert lengths, or genomic coverage."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-samples", type=int, default=198)
    args = parser.parse_args()
    doc = build(args.data, expected=args.expected_samples)
    with args.out.open("x") as stream:
        stream.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
