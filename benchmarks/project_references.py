"""Project-native MiCall reference diagnostics. Never used by the assembler."""
import csv
import hashlib
from pathlib import Path

from Bio.Align import PairwiseAligner


def reference_names(projects, project_code):
    project = projects["projects"][project_code]
    names = {name for region in project["regions"]
             for name in region["seed_region_names"]}
    return sorted(name for name in names
                  if name in projects["regions"]
                  and projects["regions"][name]["is_nucleotide"])


def choose_reference(iva_dir, projects, project_code):
    """Select one reference from the IVA arm's MiCall remap, not the Ivanka arm."""
    names = reference_names(projects, project_code)
    candidates = []
    for path in (Path(iva_dir) / "remap_counts.csv",
                 Path(iva_dir) / "scratch" / "remap_counts.csv"):
        if not path.is_file():
            continue
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                label = row.get("type", "")
                if not label.startswith("remap-final "):
                    continue
                label = label.removeprefix("remap-final ")
                _, _, label = label.partition("-")
                matches = (label, label.removesuffix("-excluded"),
                           label.removesuffix("-seed-excluded"))
                name = next((candidate for candidate in matches if candidate in names), None)
                if name is not None:
                    candidates.append((int(row.get("count") or 0), name))
        break
    if candidates:
        _, name = max(candidates, key=lambda x: (x[0], x[1]))
    elif len(names) == 1:
        name = names[0]
    else:
        raise ValueError("Cannot determine IVA-selected reference for " + project_code)
    sequence = "".join(projects["regions"][name]["reference"]).upper()
    if not sequence or any(c not in "ACGT" for c in sequence):
        raise ValueError("Invalid nucleotide project reference: " + name)
    return name, sequence


def final_max_sequences(directory):
    path = next((p for p in (Path(directory) / "conseq.csv",
                            Path(directory) / "scratch" / "conseq.csv") if p.is_file()), None)
    if path is None:
        return []
    with path.open(newline="") as handle:
        return [r.get("sequence", "").upper()
                for r in csv.DictReader(handle)
                if r.get("consensus-percent-cutoff") == "MAX" and r.get("sequence")]


def raw_contigs(directory, maximum=16):
    path = next((p for p in (Path(directory) / "unstitched_contigs.csv",
                            Path(directory) / "scratch" / "unstitched_contigs.csv")
                 if p.is_file()), None)
    if path is None:
        return [], 0
    with path.open(newline="") as handle:
        seqs = [r.get("contig", "").upper() for r in csv.DictReader(handle)
                if r.get("contig")]
    return sorted(seqs, key=len, reverse=True)[:maximum], len(seqs)


def aligned_to_project_reference(iva_dir, ivanka_dir, projects, project_code):
    """Same IVA-selected project seed reference for both real final MiCall arms.

    Diagnostic only. Do not replace the strict IVA/Ivanka acceptance test.
    """
    name, sequence = choose_reference(iva_dir, projects, project_code)
    aligner = PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1
    result = {"name": name, "reference_length": len(sequence),
              "reference_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
              "source": "MiCall project seed reference selected by IVA final remap",
              "method": "local alignment of final MAX consensus",
              "project_code": project_code}
    for arm, path in (("iva", iva_dir), ("ivanka", ivanka_dir)):
        seqs = final_max_sequences(path)
        raw, raw_total = raw_contigs(path)
        result[arm + "_raw_total"] = raw_total
        result[arm + "_raw_scored"] = len(raw)
        result[arm + "_raw_longest"] = max(map(len, raw), default=0)
        result[arm + "_best_raw_local_score"] = (
            max((float(aligner.score(sequence, s)) for s in raw), default=None))
        result[arm + "_max_count"] = len(seqs)
        result[arm + "_best_local_score"] = (
            max((float(aligner.score(sequence, s)) for s in seqs), default=None))
    return result
