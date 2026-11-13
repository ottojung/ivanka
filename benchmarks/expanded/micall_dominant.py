"""Score final MiCall MAX outputs with the common local-alignment function."""
import hashlib
from pathlib import Path

from benchmarks.project_references import final_max_sequences
from .score import reference_truth, score_sequences

SCORE_ORIGIN = "micall_final_max_reference_panel_v1"


def evaluate_final_alignment(manifest, truth_path, micall_folder):
    """Evaluate a completed MiCall pipeline, never its assembly FASTA."""
    root = Path(micall_folder)
    source = next((p for p in (root/"conseq.csv",
                               root/"scratch/conseq.csv") if p.is_file()),
                  None)
    sequences = final_max_sequences(root)
    if source is None or not sequences:
        raise ValueError("missing final MiCall MAX consensus output")
    truth = reference_truth(manifest, truth_path)
    result = score_sequences(manifest, truth_path, sequences)
    return {"score": result["score"],
            "dominant_exact": result["dominant_exact"],
            "score_origin": SCORE_ORIGIN,
            "source": {
                "reference_count": 1,
                "reference_length": len(truth),
                "final_max_contig_count": result["contig_count"],
                "best_contig_length": result["best_contig_length"],
                "source_output": str(source.relative_to(root)),
                "conseq_csv_sha256": hashlib.sha256(
                    source.read_bytes()).hexdigest(),
            }}
