"""CPU-only authentic MiCall A/B for single-placement molecule-conserving remap.

Only saved sample files are read. Original qname multiplicities and observed
read sequences are invariant. Reassignments may still bias haplotype abundance;
a score increase alone is never evidence of biological validity.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from exact_pair_remap_equivalence import verified_source_references
from experimental_pair_safe_replay import read_csv, aligned_multiset
from experimental_pair_safe_final_ab import (
    regenerate, row_multiset, max_rows, score_exact_panel,
)
from experimental_phase_marker_retention import audit_phase_markers
from experimental_single_placement import write_candidate


def run(saved, destination, selected, target, maximum_moves=None,
        maximum_span=1000, projects_file=None, hxb2_file=None,
        protect_depth=None):
    from micall.core.sam2aln import sam2aln

    saved, destination = Path(saved), Path(destination)
    if destination.exists():
        raise ValueError("Evidence directory must not already exist")
    if (projects_file is None) != (hxb2_file is None):
        raise ValueError("Frozen reference inputs must be supplied together")
    if len(selected) < 2 or len(set(selected)) != len(selected) or target not in selected:
        raise ValueError("Require distinct selected references including target")
    scratch = saved / "scratch"
    source = scratch / "remap.csv"
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    refs = verified_source_references(
        read_csv(scratch / "stitched_contigs.csv"),
        read_csv(scratch / "remap_conseq.csv"), selected)
    originals = read_csv(source)
    # In-memory preflight before writing any experimental mapping.
    from experimental_single_placement import reallocate
    _, stats = reallocate(originals, refs, target, maximum_moves, maximum_span,
                          protect_depth)
    destination.mkdir(parents=True)
    candidate_remap = destination / "single-placement-remap.csv"
    with candidate_remap.open("w") as handle:
        written = write_candidate(originals, refs, target, handle,
                                  maximum_moves=maximum_moves,
                                  maximum_span=maximum_span,
                                  protect_depth=protect_depth)
    if written != stats:
        raise AssertionError("Preflight differs from serialized candidate")
    for arm, remap in (("control", source), ("candidate", candidate_remap)):
        with (remap.open() as input_csv,
              (destination / (arm + "-aligned.csv")).open("w") as aligned,
              (destination / (arm + "-failed.csv")).open("w") as failed,
              (destination / (arm + "-clipping.csv")).open("w") as clipping,
              (destination / (arm + "-conseq-ins.csv")).open("w") as inserts):
            sam2aln(input_csv, aligned, insert_csv=inserts,
                    failed_csv=failed, clipping_csv=clipping)
    if aligned_multiset(destination / "control-aligned.csv") != aligned_multiset(
            scratch / "aligned.csv"):
        raise AssertionError("Real MiCall baseline sam2aln differs from saved")
    if Counter(r["cause"] for r in read_csv(destination / "control-failed.csv")) != Counter(
            r["cause"] for r in read_csv(destination / "candidate-failed.csv")):
        raise AssertionError("Reassignment changed MiCall failure causes")
    for suffix, saved_name in (("conseq-ins.csv", "conseq_ins.csv"),
                               ("clipping.csv", "clipping.csv")):
        if read_csv(destination / ("control-" + suffix)) != read_csv(
                scratch / saved_name):
            raise AssertionError("Real MiCall baseline differs from saved " + saved_name)
    for arm in ("control", "candidate"):
        regenerate(scratch, destination, destination / arm, arm)
    if row_multiset(destination / "control/conseq.csv") != row_multiset(
            scratch / "conseq.csv"):
        raise AssertionError("Real MiCall baseline final consensus differs from saved")
    before = max_rows(destination / "control/conseq.csv")
    after = max_rows(destination / "candidate/conseq.csv")
    retention = audit_phase_markers(before, after)
    result = {
        "status": "EXPERIMENTAL_NOT_QUALIFIED",
        "target": target,
        "protected_q15_source_depth": protect_depth,
        "source_remap_sha256": source_digest,
        "molecule_conservation": stats,
        "baseline_reproduced_exactly": True,
        "baseline_region_251mer_loss": sum(
            v["lost"] for v in retention["sizes"]["251"]["regions"].values()),
        "phase_marker_retention": retention,
        "mask_delta_by_region": {
            region: before[region].lower().count("x") - after[region].lower().count("x")
            for region in sorted(before)
        },
        "caveat": "No new molecules, but allocation may bias phased haplotypes. "
                  "Do not merge or qualify from this CPU-only replay.",
    }
    if projects_file is not None:
        result["frozen_panel"] = score_exact_panel(
            destination / "control", destination / "candidate",
            projects_file, hxb2_file)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_digest:
        raise AssertionError("Original MiCall input changed during replay")
    (destination / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved_ivanka", type=Path)
    parser.add_argument("new_evidence_directory", type=Path)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--maximum-moves", type=int)
    parser.add_argument("--maximum-span", type=int, default=1000)
    parser.add_argument("--protect-depth", type=int)
    parser.add_argument("--projects-json", type=Path)
    parser.add_argument("--hxb2-fasta", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.saved_ivanka, args.new_evidence_directory,
                         args.reference, args.target, args.maximum_moves,
                         args.maximum_span, args.projects_json, args.hxb2_fasta,
                         args.protect_depth),
                     indent=2))


if __name__ == "__main__":
    main()
