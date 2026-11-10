"""Evaluate a synthetic assembled FASTA against hidden known generating genomes.

Use ONLY after assembly, never as input to assembler, seed selection or MiCall.
A high reference-panel score alone cannot certify viral phase on real reads.
"""
import argparse
import json
from pathlib import Path

from Bio import SeqIO
from Bio.Align import PairwiseAligner


def _sequences(file):
    with Path(file).open() as source:
        return {r.id: str(r.seq).upper() for r in SeqIO.parse(source, "fasta")}


def evaluate(truth_file, candidate_file):
    truth = _sequences(truth_file)
    candidates = _sequences(candidate_file)
    if not truth or not candidates:
        raise ValueError("truth and candidate FASTAs must both be nonempty")
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1
    scores = {
        name: max(float(aligner.score(sequence, candidate))
                  for candidate in candidates.values())
        for name, sequence in truth.items()
    }
    full_truth = set(truth.values())
    exact_recovered = sum(any(c == truth_seq for c in candidates.values())
                          for truth_seq in truth.values())
    return {
        "synthetic_only": True,
        "known_truth": True,
        "best_global_truth_score_sum": sum(scores.values()),
        "per_truth_best_global_score": scores,
        "exact_truth_haplotypes_recovered": exact_recovered,
        "truth_haplotypes": len(truth),
        "candidate_contigs": len(candidates),
        "nontruth_full_length_contigs": sum(
            len(c) in {len(t) for t in full_truth} and c not in full_truth
            for c in candidates.values()),
        "qualification_effect": "none",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("truth_fasta", type=Path)
    p.add_argument("candidate_fasta", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    report = evaluate(a.truth_fasta, a.candidate_fasta)
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if a.output:
        with a.output.open("x") as f:
            f.write(data)
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
