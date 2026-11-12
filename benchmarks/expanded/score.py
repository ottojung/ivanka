"""Evaluate assembled sequences against withheld synthetic dominant truth.

This module runs ONLY after all assembly processes have exited. Neither
assembler commands nor container mounts contain the truth or its path.
"""
from pathlib import Path
import zlib  # noqa: F401  # Load libz before NumPy-backed alignment libraries.

# All legal IUPAC DNA ambiguity codes are valid assembled nucleotides.
# An ambiguous code remains a mismatch to a known A/C/G/T truth base.
_DNA = "ACGTRYSWKMBDHVN"
_REVERSE = str.maketrans(_DNA, "TGCAYRSWMKVHDBN")


def reverse_complement(seq):
    return seq.translate(_REVERSE)[::-1]


def read_fasta(path):
    """Return all contigs, including short candidates; empty FASTA is valid."""
    sequences = []
    fragment = []
    seen = False
    with Path(path).open() as stream:
        for line in stream:
            line = line.strip()
            if line.startswith(">"):
                if seen:
                    sequences.append("".join(fragment).upper())
                seen, fragment = True, []
            elif line:
                if not seen:
                    raise ValueError("FASTA sequence before header")
                fragment.append(line)
    if seen:
        sequences.append("".join(fragment).upper())
    if any(not c or set(c) - set(_DNA) for c in sequences):
        raise ValueError("invalid FASTA assembled sequence")
    return sequences


def dominant_truth_score(manifest, truth_path, fasta_path):
    """Standalone FASTA-to-truth *diagnostic*, never pipeline qualification."""
    return score_sequences(manifest, truth_path, read_fasta(fasta_path))


def score_sequences(manifest, truth_path, assembled):
    """Score supplied sequences; callers determine whether they are MiCall final.

    Major = highest nominal generating fraction. An exact 50/50 mixture
    allows either co-dominant genome. Haplotype phase is not inferred.
    """
    try:
        from Bio.Align import PairwiseAligner
    except ImportError as exc:
        raise RuntimeError("Biopython is required for independent truth scoring") from exc
    truth = read_fasta(truth_path)
    fractions = manifest["nominal_fractions"]
    if len(fractions) != len(truth) or not truth:
        raise ValueError("inconsistent hidden truth or haplotype frequencies")
    highest = max(fractions)
    majors = [seq for seq, abundance in zip(truth, fractions)
              if abundance == highest]
    if not assembled:
        return {"score": 0.0, "dominant_exact": False, "contig_count": 0,
                "best_contig_length": 0}
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1
    # A DNA assembler's orientation is arbitrary: reversing a contig
    # changes neither the reconstructed genome nor its biological validity.
    scores = [(max(aligner.score(ref, contig),
                   aligner.score(ref, reverse_complement(contig))) / len(ref),
               len(contig))
              for ref in majors for contig in assembled]
    best, length = max(scores, key=lambda item: (item[0], -abs(item[1]-len(majors[0]))))
    return {
        "score": round(max(0.0, min(1.0, best)), 8),
        "dominant_exact": any(
            seq in assembled or reverse_complement(seq) in assembled
            for seq in majors),
        "contig_count": len(assembled), "best_contig_length": length,
        "longest_contig_length": max(map(len, assembled)),
    }
