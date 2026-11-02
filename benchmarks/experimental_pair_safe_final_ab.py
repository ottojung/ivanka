"""Recompute final MiCall MAX consensuses from pair-safe remap replay evidence.

This scientific A/B uses the genuine MiCall aln2counts on saved data. It
REFUSES to interpret the candidate unless the baseline reproduces the
original final MiCall consensus exactly. It is not a full 198 qualification.
"""
import argparse
import csv
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path


OUTPUTS = (
    "nuc", "amino", "insertions", "conseq", "failed_align",
    "coverage_summary", "conseq_region", "amino_details",
    "genome_coverage", "nuc_details", "conseq_all",
    "minimap_hits", "alignments", "alignments_unmerged",
    "alignments_intermediate", "alignments_overall",
    "concordance", "concordance_detailed", "concordance_seed",
)


def rows(path):
    with Path(path).open() as handle:
        return list(csv.DictReader(handle))


def row_multiset(path):
    return Counter(tuple(sorted(record.items())) for record in rows(path))


def max_rows(path):
    return {r["region"]:r["sequence"] for r in rows(path)
            if r.get("q-cutoff") == "15"
            and r.get("consensus-percent-cutoff") == "MAX"}


def regenerate(scratch, evidence_dir, target_dir, arm):
    from micall.core.aln2counts import aln2counts

    scratch, evidence_dir, target_dir = map(
        Path, (scratch, evidence_dir, target_dir))
    if target_dir.exists():
        raise ValueError("Output directory must be new")
    target_dir.mkdir(parents=True)
    inputs = {
        "aligned_csv":evidence_dir / (arm + "-aligned.csv"),
        "clipping_csv":evidence_dir / (arm + "-clipping.csv"),
        "conseq_ins_csv":evidence_dir / (arm + "-conseq-ins.csv"),
        "g2p_aligned_csv":scratch / "g2p_aligned.csv",
        "remap_conseq_csv":scratch / "remap_conseq.csv",
        "contigs_csv":scratch / "contigs.csv",
    }
    with ExitStack() as stack:
        opened = {name:stack.enter_context(path.open())
                  for name, path in inputs.items()}
        outputs = {name+"_csv":stack.enter_context(
                   (target_dir / (name+".csv")).open("w"))
                   for name in OUTPUTS}
        aln2counts(opened["aligned_csv"],
                   outputs["nuc_csv"], outputs["amino_csv"],
                   outputs["insertions_csv"], outputs["conseq_csv"],
                   outputs["failed_align_csv"],
                   coverage_summary_csv=outputs["coverage_summary_csv"],
                   clipping_csv=opened["clipping_csv"],
                   conseq_ins_csv=opened["conseq_ins_csv"],
                   g2p_aligned_csv=opened["g2p_aligned_csv"],
                   remap_conseq_csv=opened["remap_conseq_csv"],
                   conseq_region_csv=outputs["conseq_region_csv"],
                   amino_detail_csv=outputs["amino_details_csv"],
                   genome_coverage_csv=outputs["genome_coverage_csv"],
                   nuc_detail_csv=outputs["nuc_details_csv"],
                   contigs_csv=opened["contigs_csv"],
                   conseq_all_csv=outputs["conseq_all_csv"],
                   minimap_hits_csv=outputs["minimap_hits_csv"],
                   alignments_csv=outputs["alignments_csv"],
                   alignments_unmerged_csv=outputs["alignments_unmerged_csv"],
                   alignments_intermediate_csv=outputs["alignments_intermediate_csv"],
                   alignments_overall_csv=outputs["alignments_overall_csv"],
                   concordance_csv=outputs["concordance_csv"],
                   concordance_detailed_csv=outputs["concordance_detailed_csv"],
                   concordance_seed_csv=outputs["concordance_seed_csv"])


FROZEN_PANEL_SHA256 = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"


def score_exact_panel(control_dir, experimental_dir, projects_file, hxb2_file):
    from Bio import SeqIO
    from reference_panel import build_reference_panel, best_panel_alignment, panel_sha256
    from project_references import final_max_sequences

    with Path(projects_file).open() as handle:
        catalog = json.load(handle)
    with Path(hxb2_file).open() as handle:
        reference = next(SeqIO.parse(handle, "fasta")).seq
    panel = build_reference_panel(catalog, reference)
    if panel_sha256(panel) != FROZEN_PANEL_SHA256:
        raise ValueError("Reference panel differs from immutable 33-reference control")
    return {
        "reference_count":len(panel),
        "reference_panel_sha256":FROZEN_PANEL_SHA256,
        "control":best_panel_alignment(final_max_sequences(control_dir), panel),
        "experimental":best_panel_alignment(final_max_sequences(experimental_dir), panel),
    }


def run(saved_ivanka, evidence, destination, projects_file=None, hxb2_file=None):
    from experimental_pair_safe_replay import read_csv
    root, evidence, destination = map(Path,(saved_ivanka,evidence,destination))
    if destination.exists():
        raise ValueError("Final A/B directory must be new")
    prior = json.loads((evidence/"evidence.json").read_text())
    if (not prior["replayed_original_exactly"]
            or not prior["all_original_aligned_records_preserved"]
            or not prior["failure_causes_unchanged"]):
        raise ValueError("MiCall sam2aln replay has not passed safety checks")
    scratch = root/"scratch"
    destination.mkdir(parents=True)
    for arm in ("control","experimental"):
        regenerate(scratch,evidence,destination/arm,arm)
    original = row_multiset(scratch/"conseq.csv")
    baseline = row_multiset(destination/"control/conseq.csv")
    if original != baseline:
        raise AssertionError("Baseline aln2counts is NOT identical to saved MiCall")
    old, proposed = (max_rows(destination / arm / "conseq.csv")
                     for arm in ("control","experimental"))
    if set(old) != set(proposed):
        raise AssertionError("Candidate changed region identity")
    changes = {k:{"original_masked":old[k].lower().count("x"),
                  "candidate_masked":proposed[k].lower().count("x"),
                  "bases_changed":sum(a!=b for a,b in zip(old[k],proposed[k]))
                        + abs(len(old[k])-len(proposed[k]))}
               for k in sorted(old) if old[k] != proposed[k]}
    report = {"baseline_final_MAX_reproduced_exactly":True,
              "regions_changed":changes,
              "candidate_has_more_calls":any(
                  old[k].lower().count("x") > proposed[k].lower().count("x")
                  for k in changes),
              "caveat":"Not qualified: redistributed reads are not independent molecules "
                       "or proved haplotypes, and no PSI or panel score is asserted."}
    if (projects_file is None) != (hxb2_file is None):
        raise ValueError("Specify both frozen reference inputs or neither")
    if projects_file is not None:
        report["panel_alignment"] = score_exact_panel(
            destination/"control",destination/"experimental",
            projects_file,hxb2_file)
        report["panel_score_delta"] = (
            report["panel_alignment"]["experimental"]["score"]
            - report["panel_alignment"]["control"]["score"])
    (destination/"comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("saved_ivanka_artifacts",type=Path)
    ap.add_argument("safe_remap_replay_directory",type=Path)
    ap.add_argument("new_final_ab_directory",type=Path)
    ap.add_argument("--projects-json",type=Path)
    ap.add_argument("--hxb2-fasta",type=Path)
    args=ap.parse_args()
    print(json.dumps(run(args.saved_ivanka_artifacts,
                         args.safe_remap_replay_directory,
                         args.new_final_ab_directory,
                         args.projects_json,args.hxb2_fasta),indent=2))


if __name__=="__main__":
    main()
