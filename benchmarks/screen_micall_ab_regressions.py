"""Conservative read-only MiCall original-read A/B regression screen.

This is a *negative safety gate*: a clean comparison is NOT a proof of
biological equivalence, correct haplotype phase, or distinct DNA molecules.
"""
import argparse
import json
from pathlib import Path
from snv_micall_ab_diagnostics import compare as q15_compare
from snv_remap_assignment_ab import compare as remap_compare


def assess(baseline, candidate):
    nucleotide=q15_compare(baseline,candidate)
    assignment=remap_compare(baseline,candidate)
    failures={}
    def fail(metric,value):
        if value:failures[metric]=value
    fail("lost_q15_alleles_ge_10",nucleotide[
        "baseline_q15_allele_calls_ge_10_lost_on_matched_loci"])
    fail("high_depth_q15_sites_dropped_under_100",nucleotide[
        "matched_loci_dropped_below_depth_100"])
    fail("previous_high_depth_q15_loci_missing",nucleotide[
        "baseline_high_depth_loci_missing_candidate"])
    fail("baseline_q15_loci_unmatched",nucleotide["baseline_only_q15_nuc_loci"])
    fail("baseline_q15_max_sequences_changed",nucleotide[
        "baseline_max_sequence_rows_lost"])
    fail("original_read_pairs_reassigned_between_contigs",assignment[
        "same_original_qname_placed_on_different_reference_sequence"])
    fail("baseline_original_strict_pair_assignments_lost",assignment[
        "original_qnames_only_baseline"])
    return {
        "schema_version":"ivanka.micall_original_pair_ab_regression_screen.v1",
        "conservative_observed_regressions":failures,
        "conservative_screen_status":(
            "negative_evidence_detected_manual_review_required"
            if failures else "no_screened_regression_detected_not_biological_clearance"),
        "automatic_reconstruction_release_permitted":False,
        "full_length_haplotype_phase_verified":False,
        "independent_physical_molecule_counts_verified":False,
        "raw_fastq_mate_provenance_verified_by_this_screen":False,
        "original_micall_sources_modified":False,
        "q15_nucleotide_report":nucleotide,
        "original_pair_remap_report":assignment,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline",type=Path)
    parser.add_argument("experiment",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=assess(args.baseline,args.experiment)
    value=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.output:
        dest=args.output.resolve()
        for source in (args.baseline,args.experiment):
            root=source.resolve()
            if dest==root or root in dest.parents:
                parser.error("Refusing output inside original MiCall results")
        if dest.exists():parser.error("Refusing to overwrite a prior audit")
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open("x") as out:out.write(value)
    else:print(value)
    if result["conservative_observed_regressions"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
