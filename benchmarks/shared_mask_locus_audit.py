"""Read-only diagnostic of local allele agreement across masked MiCall MAX loci.

Exact sequence agreement is not evidence of independent read coverage,
haplotype correctness, or permission to impute a masked consensus base.
"""
import argparse
import hashlib
import json
from pathlib import Path

from consensus_mask_stage_audit import max_rows, mask_runs, reverse_complement

BASES = frozenset("ACGT")


def read_fasta(path):
    """Read FASTA without silently accepting empty records."""
    entries, name, bases = [], None, []
    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    entries.append((name, "".join(bases)))
                header = line[1:].split()
                if not header:
                    raise ValueError("Empty FASTA header")
                name, bases = header[0], []
            elif name is None:
                raise ValueError("FASTA sequence before header")
            else:
                bases.append(line.upper())
    if name is not None:
        entries.append((name, "".join(bases)))
    if not entries or any(not sequence for _, sequence in entries):
        raise ValueError("Empty FASTA record or missing records")
    return entries


def exact_hits(seq, left, right, gap):
    """Report every exact flanked interval on both strands."""
    hits = []
    if not left or not right:
        return hits
    for strand, oriented in (("+", seq), ("-", reverse_complement(seq))):
        pos = oriented.find(left)
        while pos != -1:
            mid = pos + len(left)
            allele = oriented[mid:mid + gap]
            suffix = oriented[mid + gap:mid + gap + len(right)]
            if len(allele) == gap and suffix == right and set(allele) <= BASES:
                hits.append((strand, pos, allele))
            pos = oriented.find(left, pos + 1)
    return hits


def audit(regions, contigs, sample=None, region=None, min_length=0, anchor=31):
    """Assert a shared locus ONLY if every scoped contig has one identical hit."""
    if min_length < 0 or anchor < 1:
        raise ValueError("Invalid minimum length or anchor")
    scoped = [(name, seq.upper()) for name, seq in contigs if len(seq) >= min_length]
    output = []
    for (row_sample, row_region), sequence in sorted(regions.items()):
        if sample is not None and row_sample != sample:
            continue
        if region is not None and row_region != region:
            continue
        for start, end in mask_runs(sequence):
            left = sequence[start-anchor:start] if start >= anchor else ""
            right = sequence[end:end+anchor]
            anchors_valid = len(left) == len(right) == anchor and set(left + right) <= BASES
            hits, absent, ambiguous = [], [], []
            for name, seq in scoped:
                candidates = exact_hits(seq, left, right, end-start) if anchors_valid else []
                if len(candidates) == 1:
                    hits.append((name, candidates[0][2]))
                elif candidates:
                    ambiguous.append(name)
                else:
                    absent.append(name)
            alleles = {allele for _, allele in hits}
            shared = bool(scoped) and len(hits) == len(scoped) and len(alleles) == 1
            output.append({
                "sample": row_sample, "region": row_region,
                "mask_start": start, "mask_length": end-start,
                "eligible_contigs": len(scoped), "unique_matching_contigs": len(hits),
                "missing_contigs": absent, "ambiguous_contigs": ambiguous,
                "distinct_observed_alleles": len(alleles),
                "exact_shared_allele_across_scope": shared,
                "shared_allele_sha256": hashlib.sha256(next(iter(alleles)).encode()).hexdigest()
                    if shared else None,
            })
    return {
        "anchor": anchor, "minimum_contig_length": min_length,
        "interpretation": ("Exact shared sequence across an explicitly selected contig "
            "scope does not establish independent read coverage, consensus depth, "
            "or complete haplotype phase. No bases are filled or changed."),
        "mask_runs": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("raw_contigs_fasta", type=Path)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--region")
    parser.add_argument("--min-contig-length", type=int, default=0)
    parser.add_argument("--anchor", type=int, default=31)
    args = parser.parse_args()
    rows = max_rows(args.final_conseq_csv, "region")
    print(json.dumps(audit(rows, read_fasta(args.raw_contigs_fasta),
                           args.sample, args.region, args.min_contig_length,
                           args.anchor), indent=2))


if __name__ == "__main__":
    main()
