"""Versioned reference panel for alignment-based Ivanka qualification.

All sequences are sourced from the pinned MiCall IVA image (projects.json)
or the pinned dataset's HXB2 FASTA, never from an IVA/Ivanka assembly.
"""
import hashlib
import json
import re
from Bio.Align import PairwiseAligner
from Bio.Seq import Seq

try:
    import parasail  # Optional SIMD Smith-Waterman accelerator.
except ImportError:
    parasail = None


from project_references import reference_names, final_max_sequences

HCV_GENOTYPES = (
    "HCV-1a", "HCV-1b", "HCV-2a", "HCV-2b",
    "HCV-3a", "HCV-3k", "HCV-4a", "HCV-4d",
    "HCV-5a", "HCV-6a", "HCV-7a",
)

def normalize_dna(sequence):
    # MiCall includes IUPAC ambiguity symbols in some subtype genomes.
    # Mask non-ACGT nucleotide ambiguity as N, preserving every known base.
    sequence = sequence.upper().replace("-", "")
    if any(c not in "ACGTRYSWKMBDHVN" for c in sequence):
        raise ValueError("Invalid non-nucleotide reference content")
    return "".join(c if c in "ACGT" else "N" for c in sequence)


def build_reference_panel(projects, hxb2):
    """Return a deterministic, all-project panel of (name, DNA sequence)."""
    regions = projects["regions"]
    references = {"HXB2": str(hxb2).upper()}
    representatives = {}
    for name in reference_names(projects, "NFLHIVDNA"):
        match = re.match(r"^HIV1-([^-]+)-", name)
        if match:
            representatives.setdefault(match.group(1), name)
    for subtype, name in sorted(representatives.items()):
        references["HIV1-" + subtype + ":" + name] = "".join(regions[name]["reference"]).upper()
    for name in HCV_GENOTYPES:
        if name not in regions or not regions[name]["is_nucleotide"]:
            raise ValueError("Pinned MiCall reference catalog missing " + name)
        references[name] = "".join(regions[name]["reference"]).upper()
    name = "HLA-B-seed"
    if name not in regions or not regions[name]["is_nucleotide"]:
        raise ValueError("Pinned MiCall reference catalog missing HLA-B-seed")
    references[name] = "".join(regions[name]["reference"]).upper()
    # HXB2 V3 loop and immediate flanks, as a short reference for V3 amplicons.
    if len(references["HXB2"]) >= 7450:
        references["HXB2-V3-flanks-6901-7450"] = references["HXB2"][6900:7450]
    for name, sequence in list(references.items()):
        sequence = normalize_dna(sequence)
        if not sequence or not any(c in "ACGT" for c in sequence):
            raise ValueError("Invalid nucleotide reference " + name)
        references[name] = sequence
    return tuple(sorted(references.items()))


def panel_sha256(references):
    payload = json.dumps(references, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _aligner():
    aligner = PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1
    return aligner


def best_panel_alignment(sequences, references):
    """Best exact local score over every contig and every panel reference.

    We only skip comparisons when the theoretical +1-per-base upper bound
    cannot improve the current best; that does not alter the max score.
    """
    if not sequences or not references:
        raise ValueError("Missing contigs or reference panel")
    aligner = None if parasail is not None else _aligner()
    matrix = parasail.matrix_create("ACGTN", 1, -1) if parasail is not None else None
    def exact_score(sequence, reference):
        if matrix is not None and set(sequence) <= set("ACGTN"):
            result = parasail.sw_striped_16(sequence, reference, 2, 1, matrix)
            if not result.saturated:
                return float(result.score)
        nonlocal aligner
        if aligner is None:
            aligner = _aligner()
        return float(aligner.score(reference,sequence))
    best = -1.0
    winner = None
    ordered = sorted((seq.upper() for seq in sequences if seq), key=len, reverse=True)
    for index, seq in enumerate(ordered):
        if len(seq) <= best:
            continue
        rev = str(Seq(seq).reverse_complement())
        for name, reference in references:
            if min(len(seq), len(reference)) <= best:
                continue
            score = max(score_alignment for score_alignment in
                        (exact_score(seq, reference), exact_score(rev, reference)))
            if score > best:
                best = score
                winner = (name, index, len(seq))
    if winner is None:
        raise ValueError("No alignable contigs")
    return {"score": best, "reference": winner[0], "contig_index": winner[1],
            "contig_length": winner[2], "contig_count": len(ordered)}


def panel_acceptance(iva_dir, ivanka_dir, references, min_ratio=0.95):
    """Score all final MiCall MAX contigs against the SAME fixed reference panel."""
    iva = best_panel_alignment(final_max_sequences(iva_dir), references)
    ivanka = best_panel_alignment(final_max_sequences(ivanka_dir), references)
    threshold = min_ratio * iva["score"]
    return {
        "method": "best_final_max_contig_local_alignment_over_reference_panel",
        "iva_score": iva["score"], "ivanka_score": ivanka["score"],
        "threshold": threshold, "pass": iva["score"] > 0 and ivanka["score"] >= threshold,
        "iva_best_reference": iva["reference"], "ivanka_best_reference": ivanka["reference"],
        "iva_contig_count": iva["contig_count"],
        "ivanka_contig_count": ivanka["contig_count"],
        "iva_best_contig_length": iva["contig_length"],
        "ivanka_best_contig_length": ivanka["contig_length"],
        "reference_count": len(references),
        "reference_panel_sha256": panel_sha256(references),
    }
