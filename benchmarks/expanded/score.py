"""Evaluate assembled sequences against withheld synthetic dominant truth.

This module runs ONLY after all assembly processes have exited. Neither
assembler commands nor container mounts contain the truth or its path.
"""
from pathlib import Path


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
    if any(not c or set(c) - set("ACGTN") for c in sequences):
        raise ValueError("invalid FASTA assembled sequence")
    return sequences


def dominant_truth_score(manifest, truth_path, fasta_path):
    """Global alignment scores punish fragmentation and long chimeric joins.

    Major = highest nominal generating fraction. An exact 50/50 mixture has
    no uniquely defined dominant strain, so either equal-frequency truth is
    acceptable. Minority reconstruction is separately diagnosable.
    """
    try:
        from Bio.Align import PairwiseAligner
    except ImportError as exc:
        raise RuntimeError("Biopython is required for independent truth scoring") from exc
    truth = read_fasta(truth_path)
    assembled = read_fasta(fasta_path)
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
    scores = [(aligner.score(ref, contig) / len(ref), len(contig))
              for ref in majors for contig in assembled]
    best, length = max(scores, key=lambda item: (item[0], -abs(item[1]-len(majors[0]))))
    return {
        "score": round(max(0.0, min(1.0, best)), 8),
        "dominant_exact": any(seq in assembled for seq in majors),
        "contig_count": len(assembled), "best_contig_length": length,
        "longest_contig_length": max(map(len, assembled)),
    }
