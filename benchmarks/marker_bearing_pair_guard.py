"""Conservative diagnostic: identify strict original pairs that moved between
SNV cap1000 experimental and baseline remap assignments without duplication.

This is an OFFLINE diagnostic for the authenticated S48/S12 A/B artifacts. It
does NOT fabricate nuc/consensus, does NOT modify MiCall, and does NOT create
any remap output unless every moved pair can be restored to a reference whose
sequence is byte-identical in the candidate remap_conseq (no cross-contig
transplant when contig sequences changed). Pairs are original identities only.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


def load_refs(path):
    refs = {}
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != ("region", "sequence"):
            raise ValueError("Unknown remap reference CSV format")
        for row in reader:
            name = row["region"]
            if not name or not row["sequence"] or name in refs:
                raise ValueError("Missing or duplicate remap reference")
            refs[name] = row["sequence"].upper()
    return refs


def strict_pairs(remap_csv):
    raw = defaultdict(list)
    with Path(remap_csv).open(newline="") as f:
        for row in csv.DictReader(f):
            raw[row["qname"]].append(row)
    out = {}
    for qname, obs in raw.items():
        if len(obs) != 2:
            continue
        flags = []
        proper = True
        for row in obs:
            flag = int(row["flag"])
            flags.append(flag)
            if not (flag & 0x1 and flag & 0x2) or flag & (0x4 | 0x8 | 0x100 | 0x800):
                proper = False
        if not proper or obs[0]["rname"] != obs[1]["rname"]:
            continue
        if (flags[0] & 0x40) == (flags[1] & 0x40):
            continue
        out[qname] = (obs[0]["rname"], obs)
    return out


def assess_safe_restorations(baseline_dir, candidate_dir):
    """Report exact sequence/mate-valid replay options, not mere name changes.

    Even a valid byte-exact original-pair placement does NOT establish MiCall
    Q15 or MAX correctness: those require an independent downstream A/B.
    """
    from sequence_exact_pair_restoration import project_original_pairs, rows_from_file
    before = Path(baseline_dir) / "scratch"
    after = Path(candidate_dir) / "scratch"
    b = rows_from_file(before / "remap.csv")
    e = rows_from_file(after / "remap.csv")
    _,stats = project_original_pairs(
        b, load_refs(before / "remap_conseq.csv"),
        e, load_refs(after / "remap_conseq.csv"))
    moved = stats.get("changed_reference_sequence",0)
    restored = stats.get("restored_original_pairs",0)
    return {
        "strict_pairs_compared": stats.get("already_same_reference_sequence",0)+moved,
        "moved_pairs": moved,
        "reference_label_changes_not_counted_as_biological_moves": True,
        "restorable_to_identical_baseline_reference": restored,
        "unsafe_sequence_changed_or_missing_baseline_reference": moved-restored,
        "offline_q15_or_max_improvement_proven": False,
        "original_pairs_duplicated": 0,
        "restoration_applied": False,
        "reason": "offline_diagnostic_does_not_mutate_original_data",
        "breakdown":stats,
    }
