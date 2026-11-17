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


MIN_ABUNDANCE = 0.15
SCORE_SCALE = 10000


def reference_truths(manifest, truth_path):
    """Include every independently fixed generating truth at >=15%."""
    truths = read_fasta(truth_path)
    fractions = manifest["nominal_fractions"]
    if (not truths or len(truths) != len(fractions)
            or any(type(f) not in (int, float) or not isfinite(f) or f <= 0
                   for f in fractions)
            or abs(sum(fractions) - 1.0) > 1e-8):
        raise ValueError("inconsistent truth and haplotype fractions")
    return tuple((f"truth_{i}", sequence) for i, sequence
                 in enumerate(truths) if fractions[i] >= MIN_ABUNDANCE)


def reference_truth(manifest, truth_path):
    """Compatibility only when a single abundant sequence qualifies."""
    panel = reference_truths(manifest, truth_path)
    if len(panel) != 1:
        raise ValueError("multiple abundant truths; use reference_truths")
    return panel[0][1]


def score_sequences(manifest, truth_path, assembled):
    """Combined local alignment over ALL >=15% truths, not one winner.

    The per-truth maximum may reuse a contig because MiCall can represent
    nearby haplotypes as mixtures/indels. An independent HCV or V3 target
    contributes equally after length normalization; no long-genome bias.
    """
    modern = manifest.get("score_model_revision") == 2
    truths = reference_truths(manifest, truth_path)
    if not truths:
        raise ValueError("no generating truth reaches abundance threshold")
    if not modern:
        highest = max(manifest["nominal_fractions"])
        truths = tuple((f"truth_{i}", seq)
                       for i, seq in enumerate(read_fasta(truth_path))
                       if manifest["nominal_fractions"][i] == highest)
    from benchmarks.reference_panel import best_panel_alignment
    per_truth = {}
    for name, sequence in truths:
        result = (best_panel_alignment(assembled, ((name, sequence),))
                  if assembled else {"score": 0., "contig_length": 0})
        per_truth[name] = {
            "score": result["score"], "length": len(sequence),
            "fraction": result["score"] / len(sequence)}
    combined = sum(v["score"] for v in per_truth.values())
    balanced = SCORE_SCALE * sum(v["fraction"] for v in per_truth.values()) / len(truths)
    # Legacy scores remain historically interpretable; the versioned
    # new cohort explicitly opts into length-balanced multi-truth scores.
    score = balanced if modern else max(v["score"] for v in per_truth.values())
    exacts = [any(candidate == truth or
                  reverse_complement(candidate) == truth
                  for candidate in assembled) for _, truth in truths]
    exact = all(exacts) if modern else any(exacts)
    best = max(per_truth, key=lambda n: per_truth[n]["score"])
    return {
        "score": score, "combined_alignment_raw": combined,
        "balanced_alignment_score": balanced,
        "dominant_exact": exact, "contig_count": len(assembled),
        "best_contig_length": max(map(len, assembled), default=0),
        "longest_contig_length": max(map(len, assembled), default=0),
        "reference_count": len(truths), "best_reference": best,
        "reference_length": per_truth[best]["length"],
        "per_truth": per_truth, "min_abundance": MIN_ABUNDANCE,
    }


def dominant_truth_score(manifest, truth_path, fasta_path):
    return score_sequences(manifest, truth_path, read_fasta(fasta_path))
