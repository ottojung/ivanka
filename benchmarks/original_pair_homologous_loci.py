"""Source-bound read-only unphased homologous-local-locus evidence.

The same Q15 original read-pair observations are stored ONE TIME at a
locus-equivalence group, never multiplied into competing full contigs.
"""
import argparse
import json
from pathlib import Path

from original_pair_locus_evidence import evaluate_loci
from snv_original_fastq_q15 import private_output
from snv_q15_sources import verify_source
from synthetic_phase_fidelity import fasta_records


def source_bound(fasta, r1, r2, hashes, *, max_pairs=10000,
                 max_contigs=8, select="longest", short_flank=7,
                 long_flank=15, min_alleles=5,
                 min_bridge_pairs=5, min_unique_signatures=3):
    if select not in ("longest", "original"):
        raise ValueError("Unsupported original contig screening order")
    if Path(r1).resolve() == Path(r2).resolve():
        raise ValueError("Original R1 and R2 FASTQ paths must be distinct")
    sources = (fasta, r1, r2)
    for path, expected in zip(sources, hashes):
        verify_source(path, expected)
    contigs = fasta_records(fasta)
    if select == "longest":
        contigs.sort(key=lambda rec: -len(rec[1]))
    report = evaluate_loci(
        contigs, r1, r2, max_pairs=max_pairs, max_contigs=max_contigs,
        short_flank=short_flank, long_flank=long_flank,
        min_alleles=min_alleles, min_bridge_pairs=min_bridge_pairs,
        min_unique_signatures=min_unique_signatures)
    for path, expected in zip(sources, hashes):
        verify_source(path, expected)
    report["source_sha256"] = dict(zip(("ordinary_fasta","r1","r2"),hashes))
    report["source_verified_before_and_after"] = True
    report["screening_order"] = (
        "length_descending_stable" if select=="longest"
        else "original_fasta_order")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fasta", type=Path)
    parser.add_argument("r1", type=Path)
    parser.add_argument("r2", type=Path)
    for name in ("fasta","r1","r2"):
        parser.add_argument("--sha256-"+name, required=True)
    parser.add_argument("--max-pairs", type=int, default=10000)
    parser.add_argument("--max-contigs", type=int, default=8)
    parser.add_argument("--select", choices=("longest", "original"),
                        default="longest")
    parser.add_argument("--short-flank", type=int, default=7)
    parser.add_argument("--long-flank", type=int, default=15)
    parser.add_argument("--min-alleles", type=int, default=5)
    parser.add_argument("--min-bridge-pairs", type=int, default=5)
    parser.add_argument("--min-unique-signatures", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths=(args.fasta,args.r1,args.r2)
    try:
        result=source_bound(
            *paths, hashes=(args.sha256_fasta,args.sha256_r1,args.sha256_r2),
            max_pairs=args.max_pairs, max_contigs=args.max_contigs,
            select=args.select, short_flank=args.short_flank,
            long_flank=args.long_flank,min_alleles=args.min_alleles,
            min_bridge_pairs=args.min_bridge_pairs,
            min_unique_signatures=args.min_unique_signatures)
        if args.output:
            private_output(result,args.output,paths)
        else:
            print(json.dumps(result, indent=2,sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
