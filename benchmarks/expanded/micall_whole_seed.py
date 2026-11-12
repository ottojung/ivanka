"""Read-supported MiCall whole-seed final consensus for synthetic evaluation.

Never select by known generating truth. First select MiCall's final supported
region; then retrieve the matching finalized seed-wide Q15 MAX sequence.
"""
import csv
from pathlib import Path

from .micall_dominant import digest, final_rows, select_final_dominant
from .score import score_sequences

SCORE_ORIGIN = "micall_final_dominant_whole_seed_truth_v2"
DNA = frozenset("ACGTRYSWKMBDHVNX")


def select_whole_seed(folder):
    folder = Path(folder)
    selected = select_final_dominant(folder)
    region_rows, _ = final_rows(folder)
    expected_sample = region_rows[0]["sample"]
    path = folder / "conseq_all.csv"
    if not path.is_file():
        raise ValueError("missing finalized whole-seed conseq_all.csv")
    with path.open(newline="") as source:
        reader = csv.DictReader(source)
        required = {"sample", "seed", "region", "q-cutoff",
                    "consensus-percent-cutoff", "seed-offset", "sequence"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise ValueError("unsupported finalized whole-seed schema")
        rows = [r for r in reader if r.get("seed") == selected["region"]
                and r.get("region") == "" and r.get("q-cutoff") == "15"
                and r.get("consensus-percent-cutoff") == "MAX"]
    if len(rows) != 1:
        raise ValueError("final dominant seed has no unique whole-seed MAX")
    row = rows[0]
    if row["sample"] != expected_sample:
        raise ValueError("whole-seed consensus belongs to another sample")
    if not row["seed-offset"].isdigit():
        raise ValueError("invalid finalized whole-seed offset")
    sequence = row["sequence"].upper().strip()
    if not sequence or set(sequence) - DNA:
        raise ValueError("invalid finalized whole-seed nucleotide consensus")
    selected["short_region_sha256"] = selected.pop("sequence_sha256")
    selected["short_region_length"] = len(selected["sequence"])
    selected["sequence"] = sequence
    selected["whole_seed_offset"] = int(row["seed-offset"])
    selected["whole_seed_length"] = len(sequence)
    selected["whole_seed_conseq_sha256"] = digest(path)
    return selected


def evaluate_whole_seed(manifest, truth_path, micall_folder):
    """Only *after* read-supported selection do we inspect hidden truth."""
    selected = select_whole_seed(micall_folder)
    scored = score_sequences(manifest, truth_path, [selected["sequence"]])
    return {"score": scored["score"], "dominant_exact": scored["dominant_exact"],
            "score_origin": SCORE_ORIGIN,
            "source": {k: v for k, v in selected.items() if k != "sequence"}}
