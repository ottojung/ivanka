"""Necessary per-position support bound for exclusive HCV read-pair assignment.

Consumes the existing read-only shared-locus audit output. This is a counting
obstruction, NOT proof that any particular contig can be rescued, and NOT
a replacement for MiCall's merged quality/coverage calculation.
"""
import argparse
import json
from pathlib import Path


def exclusive_support_bound(report, required_depth=100):
    """Bound how many alternatives can each receive depth from unique qnames.

    No single original read pair may contribute to more than one hypothesis at
    a fixed shared site. The allele-matching, qname-deduplicated pooled counts
    are an UPPER bound on physical molecule support, not independent molecules.
    """
    if type(required_depth) is not int or required_depth < 1:
        raise ValueError("Required depth must be a positive integer")
    names = report["reference_names"]
    counts = report["pooled_deduplicated"]["per_position"]
    if (not isinstance(names, list) or len(names) < 2
            or any(not isinstance(n, str) or not n for n in names)
            or len(set(names)) != len(names)
            or not isinstance(counts, list) or not counts
            or any(type(n) is not int or n < 0 for n in counts)):
        raise ValueError("Invalid shared-locus reference or pair-count data")
    per_site_max = [n // required_depth for n in counts]
    upper_bound = min(per_site_max)
    all_needed = len(names) * required_depth
    min_support = min(counts)
    return {
        "distinct_hypotheses_requested": len(names),
        "target_q15_pair_depth": required_depth,
        "minimum_pooled_allele_matching_pair_ids": min_support,
        "per_site_exclusive_hypotheses_upper_bound": per_site_max,
        "all_hypotheses_possible_under_exclusive_assignment_necessary_test":
            min_support >= all_needed,
        "maximum_hypotheses_at_full_depth_upper_bound":
            min(upper_bound, len(names)),
        "minimum_missing_pair_site_votes_to_cover_all":
            max(0, all_needed - min_support),
        "interpretation": (
            "Necessary per-site pigeonhole bound: under one original qname "
            "per site per alternative, K hypotheses with D support each "
            "need at least K*D pooled allele-matching original qnames at "
            "every shared site. A failure proves no exclusive assignment "
            "can meet every demand. Passing does not prove a feasible "
            "assignment, actual MiCall coverage, independent physical "
            "molecules, or any haplotype phase."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("read_only_shared_locus_audit_json", type=Path)
    parser.add_argument("--required-depth", type=int, default=100)
    args = parser.parse_args()
    report = json.loads(args.read_only_shared_locus_audit_json.read_text())
    print(json.dumps(exclusive_support_bound(report, args.required_depth),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
