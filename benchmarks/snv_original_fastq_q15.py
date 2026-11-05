"""Read-only source-bound Q15 check of Ivanka's explicitly unphased SNV TSV.

Counts original paired FASTQ IDs, not mapping rows, overlapping 31-mers or
independent biological molecules. Never assigns full-length haplotype phase.
"""
import argparse
import csv
import json
import os
from pathlib import Path

from snv_q15_fastq import iter_original_pairs
from snv_q15_sources import bound_candidates, verify_source
from snv_q15_evidence import observe_pair, summarized


def audit(audit_tsv, ordinary_fasta, original_r1, original_r2, *,
          expected_hashes, min_phred=15, min_pairs=10, max_pairs=50000):
    if (type(min_phred) is not int or min_phred < 15
            or type(min_pairs) is not int or min_pairs < 1
            or type(max_pairs) is not int or not 1 <= max_pairs <= 50000):
        raise ValueError("Invalid research evidence constraints")
    sources = {"audit_tsv": audit_tsv, "ordinary_fasta": ordinary_fasta,
               "original_r1": original_r1, "original_r2": original_r2}
    sha = {key: verify_source(path, expected_hashes[key])
           for key, path in sources.items()}
    candidates = bound_candidates(audit_tsv, ordinary_fasta)
    states = [[] for _ in candidates]
    pair_signatures = []
    seen = set()
    for qname, mate1, mate2 in iter_original_pairs(original_r1, original_r2,
                                                  max_pairs=max_pairs):
        if qname in seen:
            raise ValueError("Duplicate original paired FASTQ identifier")
        seen.add(qname)
        pair_signatures.append((mate1[0], mate2[0]))
        for candidate, observed in zip(candidates, states):
            observed.append(observe_pair(candidate, mate1, mate2, min_phred))
    report = {
        "schema_version": "ivanka.unphased_snv_original_fastq_q15.v1",
        "source_sha256": sha,
        "pairs_scanned": len(seen),
        "q15_minimum_base_quality": min_phred,
        "observed_pair_threshold": min_pairs,
        "research_only": True,
        "reported_local_snv_candidates": len(candidates),
        "candidates": [
            summarized(candidate, states[i], pair_signatures, min_pairs)
            for i, candidate in enumerate(candidates)],
        "original_pair_ids_are_independent_physical_molecules": False,
        "full_length_haplotype_phase_inferred": False,
        "per_haplotype_read_depth_assigned": False,
        "modifies_micall_final_max": False,
        "changes_198_sample_acceptance": False,
        "interpretation": (
            "Exact Q15 allele-specific 31-mer observations in at most the "
            "first 50,000 original strictly paired FASTQ records; no remap "
            "assignment, distant phase, or molecule independence inferred"),
    }
    return report


def private_output(report, path, protected_sources):
    target = Path(path).resolve()
    for original in protected_sources:
        root = Path(original).resolve()
        if target == root or root.parent == target.parent or root.parent in target.parents:
            raise ValueError("Cannot write within original evidence directories")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("audit_tsv", "ordinary_fasta", "original_r1", "original_r2"):
        parser.add_argument(name, type=Path)
        parser.add_argument("--sha256-" + name.replace("_", "-"), required=True)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--min-pairs", type=int, default=10)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    hashes = {name: getattr(args, "sha256_" + name)
              for name in ("audit_tsv", "ordinary_fasta", "original_r1", "original_r2")}
    try:
        report = audit(
            args.audit_tsv, args.ordinary_fasta, args.original_r1,
            args.original_r2, expected_hashes=hashes, min_phred=args.min_phred,
            min_pairs=args.min_pairs, max_pairs=args.max_pairs)
        if args.output:
            private_output(report, args.output,
                           (args.audit_tsv, args.ordinary_fasta,
                            args.original_r1, args.original_r2))
        else:
            print(json.dumps(report, sort_keys=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError, csv.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
