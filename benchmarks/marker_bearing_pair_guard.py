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
        for row in csv.DictReader(f):
            refs[row["region"]] = row["sequence"].upper()
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
    baseline_dir = Path(baseline_dir)
    candidate_dir = Path(candidate_dir)
    b_refs = load_refs(baseline_dir / "scratch" / "remap_conseq.csv")
    c_refs = load_refs(candidate_dir / "scratch" / "remap_conseq.csv")
    b_pairs = strict_pairs(baseline_dir / "scratch" / "remap.csv")
    c_pairs = strict_pairs(candidate_dir / "scratch" / "remap.csv")
    moved = restorable = unsafe = 0
    for qname in set(b_pairs) & set(c_pairs):
        b_ref = b_pairs[qname][0]
        c_ref = c_pairs[qname][0]
        if b_ref == c_ref:
            continue
        moved += 1
        if b_ref in c_refs and b_refs.get(b_ref) == c_refs.get(b_ref):
            restorable += 1
        else:
            unsafe += 1
    return {
        "strict_pairs_compared": len(set(b_pairs) & set(c_pairs)),
        "moved_pairs": moved,
        "restorable_to_identical_baseline_reference": restorable,
        "unsafe_sequence_changed_or_missing_baseline_reference": unsafe,
        "original_pairs_duplicated": 0,
        "restoration_applied": False,
        "reason": "diagnostic_only_no_cross_contig_transplant",
    }
