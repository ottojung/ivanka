"""Molecule-conserving exclusive view of a remap CSV.

A projected remap (see ``conserved_pair_remap.project_remap``) appends extra
rows whose qnames carry the ``|ivanka_hypothesis=REF`` suffix. Those rows are
additional placements of the SAME original read-pair observation under an
alternative hypothesis, not independent molecules or long-range phase
evidence. Feeding them to a downstream counter as independent records would
double-count one physical observation.

This module provides the smallest correct molecule-conserving reassignment:
count each original base qname exactly once, at its original (plain-qname)
placement. The exclusive view of a projected file is therefore exactly its
original rows, in order. The projection itself is kept as a separate audit
artifact; only the exclusive view may be consumed when a claim requires one
observation per molecule.

No MiCall, MAX, acceptance, cache, image, panel, gate, or original artifact
is modified by this module. No beta/biological safety claim is made.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from remap_molecule_conservation_audit import (
    _HYPOTHESIS_MARKER,
    base_qname,
)


def _open_reader(path):
    handle = Path(path).open(newline="")
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        handle.close()
        raise ValueError("missing remap CSV header")
    if "qname" not in reader.fieldnames:
        handle.close()
        raise ValueError("missing qname column")
    return handle, reader


def exclusive_molecule_bound(path):
    """Read-only bound: distinct base qnames upper-bound independent pairs.

    Returns a dict with total rows, distinct base qnames (the molecule upper
    bound), hypothesis row counts, and the number of overcounted rows beyond
    one pair (2 records) per distinct base qname.
    """
    rows = 0
    base_rows = Counter()
    hyp_rows = 0
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("missing remap CSV header")
        if "qname" not in reader.fieldnames:
            raise ValueError("missing qname column")
        for row in reader:
            rows += 1
            base_rows[base_qname(row["qname"])] += 1
            if _HYPOTHESIS_MARKER in row["qname"]:
                hyp_rows += 1
    distinct = len(base_rows)
    return {
        "schema_version": "ivanka.molecule_conserving_effective_remap.v1",
        "rows": rows,
        "distinct_base_qnames": distinct,
        "hypothesis_marker_rows": hyp_rows,
        "overcounted_rows_beyond_one_pair_per_molecule": max(
            0, rows - 2 * distinct
        ),
        "molecule_upper_bound_pairs": distinct,
        "independent_molecules_claimed": False,
        "biological_safety_claimed": False,
    }


def require_molecule_conservation(path):
    """Fail closed unless the file needs no deduplication.

    Raises ValueError if any hypothesis-suffixed row is present. Returns the
    number of distinct base qnames otherwise. Downstream consumers that must
    count one observation per molecule should call this before counting, or
    consume :func:`derive_exclusive_view` output instead.
    """
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("missing remap CSV header")
        if "qname" not in reader.fieldnames:
            raise ValueError("missing qname column")
        bases = set()
        for row in reader:
            qname = row["qname"]
            if _HYPOTHESIS_MARKER in qname:
                raise ValueError(
                    "hypothesis-duplicated placement present; "
                    "use derive_exclusive_view for molecule-conserving counting"
                )
            bases.add(base_qname(qname))
    return len(bases)


def derive_exclusive_view(projected_path, output_path):
    """Write the molecule-conserving exclusive view.

    Keeps exactly the plain-qname (original-placement) rows in file order and
    drops every hypothesis-suffixed duplicate placement. Returns stats. The
    input file is never modified; input and output must differ.
    """
    projected_path = Path(projected_path)
    output_path = Path(output_path)
    if projected_path.resolve() == output_path.resolve():
        raise ValueError("projected input and exclusive output must be separate")
    handle, reader = _open_reader(projected_path)
    fields = reader.fieldnames
    retained = 0
    removed = 0
    try:
        with output_path.open("w", newline="") as out:
            writer = csv.DictWriter(out, fields, lineterminator="\n")
            writer.writeheader()
            for row in reader:
                base_qname(row["qname"])
                if _HYPOTHESIS_MARKER in row["qname"]:
                    removed += 1
                    continue
                writer.writerow(row)
                retained += 1
    finally:
        handle.close()
    return {
        "schema_version": "ivanka.molecule_conserving_effective_remap.v1",
        "retained_original_rows": retained,
        "removed_hypothesis_rows": removed,
        "independent_molecules_claimed": False,
        "biological_safety_claimed": False,
        "interpretation": (
            "Exclusive view counts each original base qname once at its "
            "original placement. Removed rows remain conditional/shared "
            "observations, not independent molecules."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projected_remap", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        molecules = require_molecule_conservation(args.projected_remap)
        report = {
            "molecule_conservation_preserved": True,
            "distinct_base_qnames": molecules,
        }
    elif args.output is None:
        report = exclusive_molecule_bound(args.projected_remap)
    else:
        report = derive_exclusive_view(args.projected_remap, args.output)
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
        return
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
