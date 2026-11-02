"""CPU-only replay of a candidate remap before any container integration.

Never changes saved MiCall inputs or the running qualification. This is an
*experiment* in compatible multi-mapping, not new independent read evidence.
Requires the separately installed MiCall Python package for replay.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from exact_pair_remap_equivalence import (
    compatible_copies, pooled_site_calls, verified_source_references,
)
from paired_remap_candidate_writer import serialize_original_then_alternatives


def replay(root, output, names):
    from micall.core.sam2aln import sam2aln
    root, output = Path(root), Path(output)
    if root.resolve() == output.resolve() or output.exists():
        raise ValueError("Must use a new separate evidence directory")
    if len(names) < 2 or len(names) != len(set(names)):
        raise ValueError("Select at least two distinct references")
    with (root / "scratch/stitched_contigs.csv").open() as stream:
        stitched = list(csv.DictReader(stream))
    with (root / "scratch/remap_conseq.csv").open() as stream:
        references = list(csv.DictReader(stream))
    refs = verified_source_references(stitched, references, names)
    with (root / "scratch/remap.csv").open() as stream:
        originals = list(csv.DictReader(stream))
    copies, stats = compatible_copies(refs, originals, names)
    output.mkdir(parents=True)
    augmented = output / "candidate-remap.csv"
    with augmented.open("w") as stream:
        serial_stats = serialize_original_then_alternatives(originals, copies, stream)
    results = {}
    for label, path in (
        ("baseline", root / "scratch/remap.csv"),
        ("candidate", augmented),
    ):
        with path.open() as source, (output / f"{label}-aligned.csv").open("w") as aligned, (
            output / f"{label}-failed.csv"
        ).open("w") as failed:
            sam2aln(source, aligned, failed_csv=failed)
        with (output / f"{label}-failed.csv").open() as stream:
            failures = Counter(row["cause"] for row in csv.DictReader(stream))
        with (output / f"{label}-aligned.csv").open() as stream:
            aligned_counts = Counter(row["refname"] for row in csv.DictReader(stream))
        results[label] = {
            "failure_causes": dict(failures),
            "aligned_records_by_reference": dict(aligned_counts),
        }
    before = results["baseline"]["failure_causes"].get("2refs", 0)
    after = results["candidate"]["failure_causes"].get("2refs", 0)
    if after != before:
        raise AssertionError("Candidate changed cross-reference mate failures")
    summary = {"compatible_copy_stats": stats, "serialization": serial_stats,
               "baseline": results["baseline"], "candidate": results["candidate"],
               "no_new_cross_reference_mate_failures": True,
               "caveat": "Shared qnames are alternative alignments, NOT new molecules. "
                         "This is sam2aln replay only, not final MiCall consensus."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("saved_ivanka_artifact_dir", type=Path)
    ap.add_argument("new_evidence_dir", type=Path)
    ap.add_argument("--reference", action="append", required=True)
    args = ap.parse_args()
    print(json.dumps(replay(args.saved_ivanka_artifact_dir,
                            args.new_evidence_dir, args.reference), indent=2))
