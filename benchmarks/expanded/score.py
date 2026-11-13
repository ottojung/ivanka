"""Evaluate DNA evidence with the final MiCall local-alignment scorer."""
from pathlib import Path
import zlib  # Load libz before NumPy-backed alignment libraries.

from benchmarks.reference_panel import best_panel_alignment

_DNA = "ACGTRYSWKMBDHVN"
_REVERSE = str.maketrans(_DNA, "TGCAYRSWMKVHDBN")


def reverse_complement(seq):
    return seq.translate(_REVERSE)[::-1]


def read_fasta(path):
    """Read every reference and reject malformed, empty sequences."""
    sequences, fragment, seen = [], [], False
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
    if any(not s or set(s) - set(_DNA) for s in sequences):
        raise ValueError("invalid FASTA nucleotide sequence")
    return sequences


def reference_truth(manifest, truth_path):
    """Use exactly one generating dominant genome as the reference panel."""
    truth = read_fasta(truth_path)
    fractions = manifest["nominal_fractions"]
    if not truth or len(truth) != len(fractions):
        raise ValueError("inconsistent truth and haplotype fractions")
    index = max(range(len(fractions)), key=lambda n: fractions[n])
    return truth[index]


def score_sequences(manifest, truth_path, assembled):
    """Call the exact local-alignment function used for physical samples."""
    truth = reference_truth(manifest, truth_path)
    if not assembled:
        return {"score": 0.0, "dominant_exact": False, "contig_count": 0,
                "best_contig_length": 0}
    best = best_panel_alignment(assembled, (("truth", truth),))
    exact = any(seq == truth or reverse_complement(seq) == truth
                for seq in assembled)
    return {"score": best["score"], "dominant_exact": exact,
            "contig_count": best["contig_count"],
            "best_contig_length": best["contig_length"],
            "longest_contig_length": max(map(len, assembled))}


def dominant_truth_score(manifest, truth_path, fasta_path):
    return score_sequences(manifest, truth_path, read_fasta(fasta_path))
