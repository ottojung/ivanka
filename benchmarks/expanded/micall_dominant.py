"""Select MiCall's final dominant consensus *without seeing synthetic truth*.

This is a downstream benchmark evaluator, never an Ivanka component.
MiCall's own post-remapping fragment counts choose the final MAX region.
"""
import csv
import hashlib
from pathlib import Path

from .score import score_sequences

SCORE_ORIGIN = "micall_final_dominant_truth_v1"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def final_rows(folder):
    """Only final post-MiCall consensus sequences are eligible."""
    folder = Path(folder)
    path = folder / "conseq.csv"
    if not path.is_file():
        raise ValueError("missing final MiCall conseq.csv")
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    chosen = [r for r in rows if r.get("q-cutoff") == "15"
              and r.get("consensus-percent-cutoff") == "MAX"
              and r.get("sequence", "").strip()]
    if not chosen:
        raise ValueError("no final MAX consensus: pipeline cannot qualify")
    if len({r.get("sample") for r in chosen}) != 1:
        raise ValueError("final MiCall results have inconsistent sample IDs")
    if len({r.get("region") for r in chosen}) != len(chosen):
        raise ValueError("duplicate final MAX region")
    return chosen, digest(path)


def final_counts(folder, sample):
    """Use this sample's final remap, never intermediate assignments."""
    path = Path(folder) / "remap_counts.csv"
    if not path.is_file():
        raise ValueError("missing final MiCall remap_counts.csv")
    counts = {}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            label = row.get("type", "")
            if not label.startswith("remap-final "):
                continue
            if row.get("sample") != sample:
                raise ValueError("final support belongs to another sample")
            region = label[len("remap-final "):]
            if region in counts:
                raise ValueError("ambiguous duplicate final-remap evidence")
            try:
                value = int(row["count"])
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("invalid final-remap count") from exc
            if value < 0:
                raise ValueError("negative final-remap count")
            counts[region] = value
    if not counts:
        raise ValueError("no final read-support count")
    return counts, digest(path)


def select_final_dominant(folder):
    rows, csv_hash = final_rows(folder)
    counts, counts_hash = final_counts(folder, rows[0]["sample"])
    if any(r["region"] not in counts for r in rows):
        raise ValueError("final consensus lacks original-read support provenance")
    ranked = sorted(rows, key=lambda r: (-counts[r["region"]], r["region"]))
    winner = ranked[0]
    if counts[winner["region"]] == 0:
        raise ValueError("no read-supported final dominant consensus")
    sequence = winner["sequence"].strip().upper()
    if not sequence or set(sequence) - set("ACGTRYSWKMBDHVNX"):
        raise ValueError("invalid final MiCall nucleotide consensus")
    return {
        "sequence": sequence,
        "region": winner["region"],
        "support": counts[winner["region"]],
        "equal_support_ambiguous": (len(ranked) > 1 and
                                    counts[ranked[1]["region"]] == counts[winner["region"]]),
        "final_max_regions": len(ranked),
        "conseq_csv_sha256": csv_hash,
        "remap_counts_sha256": counts_hash,
        "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
    }


def evaluate_final_dominant(manifest, truth_path, micall_folder):
    """Never choose the best truth alignment across multiple MiCall regions."""
    selected = select_final_dominant(micall_folder)
    scored = score_sequences(manifest, truth_path, [selected["sequence"]])
    return {
        "score": scored["score"],
        "dominant_exact": scored["dominant_exact"],
        "score_origin": SCORE_ORIGIN,
        "source": {k: v for k, v in selected.items() if k != "sequence"},
    }
