"""Recompute final MiCall MAX consensuses from pair-safe remap replay evidence.

This scientific A/B uses the genuine MiCall aln2counts on saved data. It
REFUSES to interpret the candidate unless the baseline reproduces the
original final MiCall consensus exactly. It is not a full 198 qualification.
"""
import argparse
import csv
import hashlib
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
    result = {}
    for record in rows(path):
        if (record.get("q-cutoff") != "15"
                or record.get("consensus-percent-cutoff") != "MAX"):
            continue
        name = record["region"]
        if name in result:
            raise ValueError(f"Repeated final MAX region: {name}")
        result[name] = record["sequence"]
    if not result:
        raise ValueError("No authentic q15 final MAX rows")
    return result


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




def consensus_change_evidence(original, candidate):
    """Diagnostic changes under ONE optimal global alignment (not phase proof)."""
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -8
    aligner.extend_gap_score = -1
    indices = aligner.align(original.upper(), candidate.upper())[0].indices
    observed = frozenset("ACGT")
    aligned = []
    for i, j in zip(*indices):
        a = original[i].upper() if i >= 0 else None
        b = candidate[j].upper() if j >= 0 else None
        aligned.append((a, b))
    return {
        "original_masked": original.lower().count("x"),
        "candidate_masked": candidate.lower().count("x"),
        "bases_changed": sum(a != b for a, b in aligned),
        "masked_bases_recovered": sum(a == "X" and b in observed
                                      for a, b in aligned),
        "existing_called_bases_changed_or_lost":
            sum(a in observed and b != a for a, b in aligned),
        "newly_masked_called_bases":
            sum(a in observed and b == "X" for a, b in aligned),
        "length_changed": len(original) != len(candidate),
        "comparison_method": "one_optimal_global_alignment_diagnostic_only",
    }



def verified_cached_iva(iva_dir, expected_sample):
    """Check the immutable cached control before any expensive MiCall replay.

    This guards artifact identity, not full-cohort scientific qualification.
    """
    iva_dir = Path(iva_dir)
    if iva_dir.name != expected_sample:
        raise ValueError("Cached IVA sample identity differs from Ivanka input")
    metadata_file = iva_dir / "baseline.json"
    consensus_file = iva_dir / "conseq.csv"
    if not metadata_file.is_file() or not consensus_file.is_file():
        raise ValueError("IVA comparison requires a complete cached IVA control")
    try:
        baseline = json.loads(metadata_file.read_text())
        control, source = baseline["iva"], baseline["provenance"]
        evidence = control["metrics"]["outputs"]["conseq.csv"]
        image = control["image_id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Malformed cached IVA control provenance") from exc
    digest = hashlib.sha256(consensus_file.read_bytes()).hexdigest()
    if (control.get("exit_code") != 0
            or source.get("all_projects") is not True
            or not source.get("fastq_sha256")
            or not source.get("hxb2_sha256")
            or not source.get("micall_project_code")
            or image != source.get("iva_image_id")
            or control.get("artifact_dir") != str(iva_dir.resolve())
            or evidence.get("exists") is not True
            or digest != evidence.get("sha256")):
        raise ValueError("Cached IVA control provenance/checksum mismatch")
    max_rows(consensus_file)
    return {"sha256": digest, "image_id": image, "sample": expected_sample}

def run(saved_ivanka, evidence, destination, projects_file=None, hxb2_file=None,
        iva_dir=None):
    from experimental_pair_safe_replay import read_csv
    root, evidence, destination = map(Path,(saved_ivanka,evidence,destination))
    if destination.exists():
        raise ValueError("Final A/B directory must be new")
    if (projects_file is None) != (hxb2_file is None):
        raise ValueError("Specify both frozen reference inputs or neither")
    if iva_dir is not None and projects_file is None:
        raise ValueError("IVA comparison requires frozen panel provenance")
    if iva_dir is not None and not any(
            p.is_file() for p in (Path(iva_dir)/"conseq.csv",
                                  Path(iva_dir)/"scratch/conseq.csv")):
        raise ValueError("Authentic cached IVA final MAX output is missing")
    cached_iva = (verified_cached_iva(iva_dir, root.parent.name)
                  if iva_dir is not None else None)
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
    changes = {k:consensus_change_evidence(old[k], proposed[k])
               for k in sorted(old) if old[k] != proposed[k]}
    report = {"baseline_final_MAX_reproduced_exactly":True,
              "regions_changed":changes,
              "candidate_has_more_calls":any(
                  item["original_masked"] > item["candidate_masked"]
                  for item in changes.values()),
              "candidate_recovers_masked_bases":any(
                  item["masked_bases_recovered"] > 0 for item in changes.values()),
              "no_called_base_loss_in_diagnostic_alignment":all(
                  not item["existing_called_bases_changed_or_lost"]
                  for item in changes.values()),
              "caveat":"Not qualified: redistributed reads are not independent molecules "
                       "or proved haplotypes; an optimal consensus alignment does not "
                       "prove phase preservation; diagnostic panel scores do not qualify "
                       "this pipeline and no PSI is established."}
    if projects_file is not None:
        report["panel_alignment"] = score_exact_panel(
            destination/"control",destination/"experimental",
            projects_file,hxb2_file)
        report["panel_score_delta"] = (
            report["panel_alignment"]["experimental"]["score"]
            - report["panel_alignment"]["control"]["score"])
        if iva_dir is not None:
            from reference_panel import panel_acceptance
            from Bio import SeqIO
            from reference_panel import build_reference_panel
            with Path(projects_file).open() as stream:
                catalog = json.load(stream)
            with Path(hxb2_file).open() as stream:
                hxb2 = next(SeqIO.parse(stream,"fasta")).seq
            immutable_panel = build_reference_panel(catalog,hxb2)
            if report["panel_alignment"]["reference_panel_sha256"] != FROZEN_PANEL_SHA256:
                raise AssertionError("Changed frozen reference panel")
            report["iva_candidate_comparison"] = panel_acceptance(
                iva_dir,destination/"experimental",immutable_panel,min_ratio=0.90)
            report["cached_iva_provenance"] = cached_iva
    (destination/"comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("saved_ivanka_artifacts",type=Path)
    ap.add_argument("safe_remap_replay_directory",type=Path)
    ap.add_argument("new_final_ab_directory",type=Path)
    ap.add_argument("--projects-json",type=Path)
    ap.add_argument("--hxb2-fasta",type=Path)
    ap.add_argument("--iva-dir",type=Path,
                    help="Verified cached IVA sample directory containing conseq.csv and baseline.json")
    args=ap.parse_args()
    print(json.dumps(run(args.saved_ivanka_artifacts,
                         args.safe_remap_replay_directory,
                         args.new_final_ab_directory,
                         args.projects_json,args.hxb2_fasta,
                         args.iva_dir),indent=2))


if __name__=="__main__":
    main()
