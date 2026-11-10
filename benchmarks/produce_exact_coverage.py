"""Run MiCall's exact_coverage calculation on the longest final MAX contig.

This intentionally reproduces analyze_kive_batches.calculate_exact_coverage_file:
one longest consensus, all original paired FASTQ read ends, exact matches,
and overlap-size=70. It does NOT use approximate Bowtie2 depth. Requires a
MiCall Python environment. The generated CSV is optional diagnostic evidence
and may be computed after benchmark timing is frozen.
"""
import argparse
import csv
from io import StringIO
from pathlib import Path


def longest_max_conseq(conseq_file):
    with Path(conseq_file).open(newline="") as reader:
        rows = list(csv.DictReader(reader))
    sequences = []
    for row in rows:
        if row.get("consensus-percent-cutoff") != "MAX":
            continue
        name = row.get("seed") or row.get("region") or ""
        seq = (row.get("sequence") or "").upper()
        if seq and "unknown" not in name.lower():
            sequences.append((name, seq))
    if not sequences:
        raise ValueError("no final MAX consensus available for exact coverage")
    # Stable first-longest selection, as in Kive's largest-conseq metric.
    return max(sequences, key=lambda x: len(x[1]))


def generate(fastq1, fastq2, conseq, output, overlap_size=70):
    from micall.utils.exact_coverage import calculate_exact_coverage
    name, sequence = longest_max_conseq(conseq)
    # MiCall's read_contigs recognizes 'ref' and 'sequence' column names.
    stream = StringIO()
    writer = csv.DictWriter(stream, ["ref", "sequence"], lineterminator="\n")
    writer.writeheader()
    writer.writerow({"ref": "longest_MAX", "sequence": sequence})
    stream.seek(0)
    bases, _, _ = calculate_exact_coverage(
        Path(fastq1), Path(fastq2), stream, overlap_size=overlap_size)
    values = bases["longest_MAX"]
    with Path(output).open("x", newline="") as out:
        writer = csv.DictWriter(
            out, ["contig", "position", "exact_coverage"],
            lineterminator="\n")
        writer.writeheader()
        for position, depth in enumerate(values, 1):
            writer.writerow({"contig": name, "position": position,
                             "exact_coverage": int(depth)})
    return {"contig": name, "bases": len(values),
            "uncovered": sum(int(v == 0) for v in values)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fastq1", type=Path)
    p.add_argument("fastq2", type=Path)
    p.add_argument("conseq_csv", type=Path)
    p.add_argument("output_csv", type=Path)
    p.add_argument("--overlap-size", type=int, default=70)
    args = p.parse_args(argv)
    if args.overlap_size < 0:
        p.error("overlap size must not be negative")
    print(generate(args.fastq1, args.fastq2, args.conseq_csv,
                   args.output_csv, args.overlap_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
