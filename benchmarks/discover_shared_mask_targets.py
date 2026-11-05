"""Discover only unambiguous, target-anchored shared-mask research candidates.

Read-only inventory: the suggested reference group is not a haplotype,
read support, molecule independence, or permission to fill a MiCall mask.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from shared_mask_locus_audit import exact_hits


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_sources(artifact_dir):
    root = Path(artifact_dir)
    final, remap = root / "conseq.csv", root / "remap_conseq.csv"
    with final.open(newline="") as stream:
        reader = csv.DictReader(stream)
        needed = {"region", "q-cutoff", "consensus-percent-cutoff", "sequence"}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError("Missing final MAX region columns")
        rows = [r for r in reader if r["q-cutoff"] == "15"
                and r["consensus-percent-cutoff"] == "MAX"]
    with remap.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"region", "sequence"}.issubset(reader.fieldnames or []):
            raise ValueError("Missing original remap-reference columns")
        refs = {}
        for r in reader:
            if not r["region"] or r["region"] in refs:
                raise ValueError("Repeated or missing remap reference name")
            refs[r["region"]] = r["sequence"].upper()
    regions = [r["region"] for r in rows]
    if len(set(regions)) != len(regions):
        raise ValueError("Duplicate Q15 MAX final region")
    return rows, refs, {"final_conseq_csv": file_sha256(final),
                        "remap_conseq_csv": file_sha256(remap)}


def discover(rows, references, anchor=31, minimum_length=20,
             region_contains="HCV"):
    if type(anchor) is not int or anchor < 1:
        raise ValueError("Expected positive flank anchor")
    if type(minimum_length) is not int or minimum_length < 1:
        raise ValueError("Expected positive minimum mask length")
    if not isinstance(region_contains, str) or not region_contains:
        raise ValueError("Expected nonempty target region selector")
    chosen, excluded = [], []
    for row in rows:
        region, seq = row["region"], row["sequence"]
        if not isinstance(region, str) or not isinstance(seq, str):
            raise ValueError("Missing final consensus region or sequence")
        if region_contains not in region:
            continue
        # MiCall Q15/MAX unresolved mask uses *lowercase x*. Uppercase X is
        # not that mask convention and must not trigger a repair candidate.
        for match in re.finditer("x+", seq):
            start, end = match.span()
            if end - start < minimum_length:
                continue
            case = {"region": region, "mask_start": start, "mask_end": end,
                    "mask_length": end-start}
            if start < anchor or end + anchor > len(seq):
                reason = "insufficient_resolved_flanks"
            else:
                left = seq[start-anchor:start].upper()
                right = seq[end:end+anchor].upper()
                if set(left + right) - set("ACGT"):
                    reason = "non_ACGT_flanks"
                else:
                    groups = defaultdict(list)
                    for name, seed in references.items():
                        hits = exact_hits(seed, left, right, end-start)
                        if len(hits) == 1:
                            groups[hits[0][2]].append(name)
                    possible = [names for names in groups.values()
                                if len(names) >= 2]
                    if len(groups) > 1:
                        reason = "competing_shared_locus_alleles"
                    elif len(possible) != 1:
                        reason = "no_unique_multi_reference_shared_locus"
                    elif region not in possible[0]:
                        reason = "target_reference_not_in_shared_group"
                    else:
                        case["selected_reference_names"] = sorted(possible[0])
                        case["target_reference_included"] = True
                        case["flank_anchor"] = anchor
                        case["shared_allele_sha256"] = hashlib.sha256(
                            next(iter(groups)).encode()).hexdigest()
                        chosen.append(case)
                        continue
            excluded.append({**case, "reason": reason})
    return {"schema_version": "ivanka.shared_mask_target_discovery.v1",
            "target_candidates": chosen,
            "rejected_masks": excluded,
            "reason_counts": dict(sorted(Counter(
                r["reason"] for r in excluded).items())),
            "phase_status": "unidentified",
            "independent_molecules_inferred": False,
            "haplotype_specific_depth_assigned": False,
            "modifies_micall_consensus": False,
            "affects_198_acceptance": False,
            "interpretation": (
                "Exact uniquely flanked same-allele groups containing the "
                "masked region itself. Not read evidence or biological phase. "
                "Excluded cases are not safe for automatic shared projection.")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--anchor", type=int, default=31)
    parser.add_argument("--minimum-length", type=int, default=20)
    parser.add_argument("--region-contains", default="HCV")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        source = args.artifact_dir.resolve(strict=True)
        rows, refs, hashes = read_sources(source)
        result = discover(rows, refs, args.anchor, args.minimum_length,
                          args.region_contains)
        result["source_sha256"] = hashes
        result["sample_count"] = len({r.get("sample", "") for r in rows})
        result["selected_region_rows"] = sum(args.region_contains in r["region"]
                                              for r in rows)
        encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output is None:
            print(encoded)
        else:
            destination = args.output.resolve()
            source_tree = source.parent if source.name == "ivanka" else source
            if destination == source_tree or source_tree in destination.parents:
                raise ValueError("Cannot write within original sample sources")
            if destination.exists():
                if not destination.is_file() or destination.read_text() != encoded:
                    raise ValueError("Cannot overwrite a changed report")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(destination, os.O_CREAT | os.O_EXCL |
                                    os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(encoded)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
