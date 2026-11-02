"""Replay a paired-template mapping candidate through REAL MiCall sam2aln.

Never modifies MiCall files or runs Podman. This is not a validated
haplotype assignment, molecule count, or 198-sample qualification.
Requires MiCall in the selected Python environment at runtime.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from exact_pair_remap_equivalence import compatible_copies, verified_source_references
from experimental_pair_safe_writer import serialize_pairs


def read_csv(path):
    with Path(path).open() as handle:
        return list(csv.DictReader(handle))


def aligned_multiset(path):
    """Ignore only MiCall's ordinal rank, which changes after insertions."""
    fields = ("refname", "qcut", "count", "offset", "seq")
    return Counter(tuple(row[k] for k in fields) for row in read_csv(path))


def no_original_alignments_lost(before, after):
    return all(after.get(k, 0) >= n for k, n in before.items())


def replay(root, destination, selected, maximum_span=1000):
    from micall.core.sam2aln import sam2aln

    root, destination = Path(root), Path(destination)
    if destination.exists():
        raise ValueError("Replay must use a new independent output directory")
    if len(selected) < 2 or len(set(selected)) != len(selected):
        raise ValueError("At least two distinct reference names are required")
    scratch = root / "scratch"
    source = scratch / "remap.csv"
    old_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    references = verified_source_references(
        read_csv(scratch / "stitched_contigs.csv"),
        read_csv(scratch / "remap_conseq.csv"), selected)
    originals = read_csv(source)
    candidate, reason_counts = compatible_copies(
        references, originals, selected, maximum_span)
    destination.mkdir(parents=True)
    alternate_csv = destination / "experimental-remap.csv"
    with alternate_csv.open("w") as target:
        written = serialize_pairs(originals, candidate, target)
    summaries = {}
    for mode, remap in (("control", source), ("experimental", alternate_csv)):
        aligned_path = destination / (mode + "-aligned.csv")
        failed_path = destination / (mode + "-failed.csv")
        with remap.open() as input_csv, aligned_path.open("w") as aligned, (
                failed_path.open("w")) as failed, (
                destination / (mode + "-clipping.csv")).open("w") as clipping:
            sam2aln(input_csv, aligned, failed_csv=failed, clipping_csv=clipping)
        summaries[mode] = {
            "aligned_rows": len(read_csv(aligned_path)),
            "failures": dict(Counter(row["cause"] for row in read_csv(failed_path))),
            "by_reference": dict(Counter(row["refname"] for row in read_csv(aligned_path))),
        }
    original_aligned = aligned_multiset(scratch / "aligned.csv")
    control_aligned = aligned_multiset(destination / "control-aligned.csv")
    experimental_aligned = aligned_multiset(destination / "experimental-aligned.csv")
    if control_aligned != original_aligned:
        raise AssertionError("MiCall control replay differs from saved original")
    if not no_original_alignments_lost(control_aligned, experimental_aligned):
        raise AssertionError("Alternative mappings erased original aligned reads")
    if summaries["control"]["failures"] != summaries["experimental"]["failures"]:
        raise AssertionError("Alternative mappings changed MiCall failure causes")
    if hashlib.sha256(source.read_bytes()).hexdigest() != old_digest:
        raise AssertionError("Original MiCall input changed during replay")
    report = {
        "source_remap_sha256":old_digest,
        "hypothetical_mapping_stats":reason_counts,
        "serialization":written,
        "control":summaries["control"],
        "experimental":summaries["experimental"],
        "replayed_original_exactly":True,
        "all_original_aligned_records_preserved":True,
        "failure_causes_unchanged":True,
        "warning":"Alternative alignments are NOT new molecules, validated phase, "
                  "or an actual consensus improvement. Experimental only.",
    }
    (destination / "evidence.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("saved_ivanka_artifacts", type=Path)
    ap.add_argument("new_evidence_directory", type=Path)
    ap.add_argument("--reference", action="append", required=True)
    ap.add_argument("--maximum-span", type=int, default=1000)
    args = ap.parse_args()
    if args.maximum_span <= 0:
        ap.error("Maximum paired-template span must be positive")
    result = replay(args.saved_ivanka_artifacts, args.new_evidence_directory,
                    args.reference, args.maximum_span)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
