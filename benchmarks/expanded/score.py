"""Evaluate DNA evidence with the final MiCall local-alignment scorer."""
from pathlib import Path
from math import isfinite
import zlib

# Import libz before scientific alignment packages on Guix hosts.
_LIBZ_LOADED = zlib.crc32(b"")


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


def reference_truths(manifest, truth_path):
    """Tie-aware panel: no arbitrary choice in an equal-abundance mixture."""
    truths = read_fasta(truth_path)
    fractions = manifest["nominal_fractions"]
    if (not truths or len(truths) != len(fractions)
            or any(type(f) not in (int, float) or not isfinite(f) or f <= 0
                   for f in fractions)):
        raise ValueError("inconsistent truth and haplotype fractions")
    highest = max(fractions)
    return tuple((f"dominant_{i}", sequence)
                 for i, (sequence, fraction) in enumerate(zip(truths, fractions))
                 if fraction == highest)


def reference_truth(manifest, truth_path):
    """Legacy compatibility for single-majority reference consumers."""
    panel = reference_truths(manifest, truth_path)
    if len(panel) != 1:
        raise ValueError("dominant truth is tied; use reference_truths")
    return panel[0][1]


def score_sequences(manifest, truth_path, assembled):
    """Call the exact local-alignment function used for physical samples."""
    truths = reference_truths(manifest, truth_path)
    if not assembled:
        return {"score": 0.0, "dominant_exact": False, "contig_count": 0,
                "best_contig_length": 0}
    from benchmarks.reference_panel import best_panel_alignment
    best = best_panel_alignment(assembled, truths)
    exact = any(seq == truth or reverse_complement(seq) == truth
                for seq in assembled for _, truth in truths)
    return {"score": best["score"], "dominant_exact": exact,
            "contig_count": best["contig_count"],
            "best_contig_length": best["contig_length"],
            "longest_contig_length": max(map(len, assembled)),
            "reference_count": len(truths), "best_reference": best["reference"],
            "reference_length": len(dict(truths)[best["reference"]])}


def dominant_truth_score(manifest, truth_path, fasta_path):
    return score_sequences(manifest, truth_path, read_fasta(fasta_path))
