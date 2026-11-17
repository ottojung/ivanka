"""Score final MiCall MAX outputs with the common local-alignment function."""
import hashlib
from pathlib import Path

from benchmarks.project_references import final_max_sequences
from .score import score_sequences

SCORE_ORIGIN = "micall_final_max_reference_panel_v1"
MULTITRUTH_SCORE_ORIGIN = "micall_final_max_abundant_truths_balanced_v2"


def evaluate_final_alignment(manifest, truth_path, micall_folder):
    """Evaluate a completed MiCall pipeline, never its assembly FASTA."""
    root = Path(micall_folder)
    source = next((p for p in (root/"conseq.csv",
                               root/"scratch/conseq.csv") if p.is_file()),
                  None)
    sequences = final_max_sequences(root)
    if source is None or not sequences:
        raise ValueError("missing final MiCall MAX consensus output")
    result = score_sequences(manifest, truth_path, sequences)
    return {"score": result["score"],
            "dominant_exact": result["dominant_exact"],
            "score_origin": (MULTITRUTH_SCORE_ORIGIN
                             if manifest.get("score_model_revision") == 2
                             else SCORE_ORIGIN),
            "source": {
                "reference_count": result["reference_count"],
                "per_truth": result["per_truth"],
                "min_abundance": result["min_abundance"],
                "combined_alignment_raw": result["combined_alignment_raw"],
                "balanced_alignment_score": result["balanced_alignment_score"],
                "reference_length": result["reference_length"],
                "best_reference": result["best_reference"],
                "final_max_contig_count": result["contig_count"],
                "best_contig_length": result["best_contig_length"],
                "source_output": str(source.relative_to(root)),
                "conseq_csv_sha256": hashlib.sha256(
                    source.read_bytes()).hexdigest(),
            }}
