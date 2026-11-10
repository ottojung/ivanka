"""Read-only diagnostic: detect duplicate read-pair placements across hypotheses.

This addresses the TtLs4qf3 open scientific gap: a numerical qualification pass
is not biological/molecular clearance if the same original read pair is
materialized as additional remap records for alternative hypotheses.
Observations are conditional on hypotheses unless independent molecules are
established by separate evidence (which this tool does NOT do).

No MiCall, MAX, acceptance, cache, image, panel, gate, or original artifact is
modified. Diagnostic only; no beta/biological safety claim.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

_HYPOTHESIS_MARKER = "|ivanka_hypothesis="


def _rows(path):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("missing remap CSV header")
        if "qname" not in reader.fieldnames:
            raise ValueError("missing qname column")
        yield from reader


def base_qname(qname):
    if qname is None:
        raise ValueError("missing qname")
    if _HYPOTHESIS_MARKER in qname:
        base, _, _ = qname.partition(_HYPOTHESIS_MARKER)
        if not base:
            raise ValueError("empty base qname before hypothesis marker")
        return base
    return qname


def audit_remap_molecule_conservation(path):
    """Report duplicate placements and hypothesis markers; fail-closed on invalid input.

    Original read pairs are normally represented by 2 SAM/remap records (mates).
    Hypothesis-suffixed qnames (`base|ivanka_hypothesis=REF`) are additional
    placements of the same original observation and are counted as duplicate
    hypothesis placements, not independent molecules.
    """
    rows = 0
    qname_rows = Counter()
    base_rows = Counter()
    hyp_qnames = set()
    hyp_refs = Counter()
    plain_qnames = set()
    for row in _rows(path):
        rows += 1
        q = row["qname"]
        qname_rows[q] += 1
        b = base_qname(q)
        base_rows[b] += 1
        if _HYPOTHESIS_MARKER in q:
            hyp_qnames.add(q)
            _, _, ref = q.partition(_HYPOTHESIS_MARKER)
            hyp_refs[ref] += 1
        else:
            plain_qnames.add(q)
    hyp_row_count = sum(qname_rows[q] for q in hyp_qnames)
    hyp_bases_with_plain_original = sum(1 for q in hyp_qnames
                                        if base_qname(q) in plain_qnames)
    # Each hypothesis placement adds mate records; base appearing >2 times means
    # more than one pair-placement group for the same original base identifier.
    duplicated_base_pairs = sum(1 for n in base_rows.values() if n > 2)
    return {
        "schema_version": "ivanka.remap_molecule_conservation_audit.v1",
        "rows": rows,
        "distinct_qnames": len(qname_rows),
        "distinct_base_qnames": len(base_rows),
        "hypothesis_marker_qnames": len(hyp_qnames),
        "hypothesis_marker_rows": hyp_row_count,
        "hypothesis_refs_row_counts": dict(hyp_refs.most_common()),
        "hypothesis_qnames_with_plain_original_base": hyp_bases_with_plain_original,
        "base_qnames_with_more_than_two_records": duplicated_base_pairs,
        "duplicate_hypothesis_placements_detected": bool(hyp_qnames),
        "molecule_conservation_preserved": not bool(hyp_qnames),
        "independent_molecules_claimed": False,
        "biological_safety_claimed": False,
        "affects_198_acceptance": False,
        "interpretation": (
            "Diagnostic only. Hypothesis-suffixed remap rows duplicate the same "
            "original read-pair observation across alternative hypotheses and are "
            "not independent molecular or long-range phase evidence. Absence of "
            "markers does not prove full biological correctness; presence "
            "indicates the molecule-conservation concern remains open for those "
            "records."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("remap_csv", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit_remap_molecule_conservation(args.remap_csv)
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
        return
    for key in ("rows", "hypothesis_marker_qnames", "duplicate_hypothesis_placements_detected",
                "molecule_conservation_preserved"):
        print(f"{key}: {report[key]}")


if __name__ == "__main__":
    main()
