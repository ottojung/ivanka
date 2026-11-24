#!/usr/bin/env python3
"""Read-only, reference-blind read-support audit of frozen-original vs candidate Ivanka.

For each case SHA in the frozen physical plan this tool:
  * reads the original Ivanka native contigs from the immutable frozen arm,
  * reads the prospective candidate native contigs and supplied read-derived
    seeds from the candidate's SHA-attested scratch archive,
  * records which native contigs were removed and whether they are exact
    (strand-canonical) duplicates of a supplied seed,
  * records the original and candidate MAX consensuses and posthoc scores,
  * computes source-read support for every distinct contig sequence using the
    pinned original MiCall exact-coverage implementation.

Only paired sequencing reads and assembler-produced contigs enter the support
computation. No reference, alignment panel, truth, score or sample identity is
used to compute support. Sample names are never written to the output.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

FROZEN = Path("/workspace/micall-frozen-seven-20261117")
CANDIDATE = Path("/workspace/ivanka-p0-novelty-canary-20261123")
FASTQ_ROOT = Path("/workspace/denovo-example-io-1/samples")
COVERAGE_TOOL = Path(
    "/workspace/micall-immutable-source-8458f9e5-20261123/micall/utils/exact_coverage.py"
)
COVERAGE_PY = FROZEN / "bench-ci-venv/bin/python"
CANON = str.maketrans("ACGT", "TGCA")


def read_fasta(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    name: str | None = None
    chunks: list[str] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    records.append((name, "".join(chunks)))
                name, chunks = line, []
            elif line and name is not None:
                chunks.append(line)
    if name is not None:
        records.append((name, "".join(chunks)))
    return records


def canonical(seq: str) -> str:
    rev = seq.translate(CANON)[::-1]
    return min(seq, rev)


def sha(seq: str) -> str:
    return hashlib.sha256(seq.encode()).hexdigest()


def max_consensus(csv_path: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not csv_path.exists():
        return out
    with csv_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("consensus-percent-cutoff") == "MAX":
                out.append(
                    {
                        "region": row.get("region", ""),
                        "len": len(row.get("sequence", "")),
                        "sha256": sha(row.get("sequence", "")),
                        "sequence": row.get("sequence", ""),
                    }
                )
    return out


def max_sequences(rows: list[dict[str, str]], label: str) -> list[tuple[str, str]]:
    return [(f"{label}-{i}", row["sequence"]) for i, row in enumerate(rows) if row.get("sequence")]


def coverage(contigs: list[tuple[str, str]], r1: Path, r2: Path, workdir: Path) -> dict[str, Any]:
    """Run pinned exact_coverage on original pairs; return per-sequence support."""
    fasta = workdir / "support.fasta"
    out = workdir / "support.csv"
    with fasta.open("w") as handle:
        for i, (_, seq) in enumerate(contigs):
            handle.write(f">c{i}\n{seq}\n")
    subprocess.run(
        [
            str(COVERAGE_PY),
            str(COVERAGE_TOOL),
            str(r1),
            str(r2),
            str(fasta),
            str(out),
            "--overlap-size",
            "70",
            "--quiet",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    per: dict[str, dict[str, list[int]]] = {}
    with out.open(newline="") as handle:
        for row in csv.DictReader(handle):
            cell = per.setdefault(row["contig"], {"exact": [], "overlap": []})
            cell["exact"].append(int(row["exact_coverage"]))
            cell["overlap"].append(int(row["exact_coverage_overlapped"]))
    result: dict[str, Any] = {}
    total_overlap = sum(
        sum(v["overlap"]) for v in per.values()
    )
    for i, (_, seq) in enumerate(contigs):
        cell = per[f"c{i}"]
        exact, overlap = cell["exact"], cell["overlap"]
        n = len(seq)
        result[f"c{i}"] = {
            "len": n,
            "sha256": sha(seq),
            "exact_mean": round(sum(exact) / n, 4) if n else 0.0,
            "zero_covered_fraction": round(sum(1 for v in exact if v == 0) / n, 4) if n else 1.0,
            "overlap_mean": round(sum(overlap) / n, 4) if n else 0.0,
            "overlap_zero_fraction": round(sum(1 for v in overlap if v == 0) / n, 4) if n else 1.0,
            "max_depth": max(exact) if exact else 0,
            "support_share": round(sum(overlap) / total_overlap, 4) if total_overlap else 0.0,
        }
    return result


def audit_case(prefix: str, work: Path) -> dict[str, Any]:
    plan = json.loads((CANDIDATE / "frozen-physical-plan.json").read_text())
    matches = [c for c in plan["cases"] if c["sample_sha256"].startswith(prefix)]
    if len(matches) != 1:
        return {"case_prefix": prefix, "error": f"plan match count {len(matches)}"}
    entry = matches[0]
    case_sha = entry["sample_sha256"]
    sample = entry["sample"]
    score_path = CANDIDATE / "physical-cases" / case_sha / "posthoc_score.json"
    score = json.loads(score_path.read_text()) if score_path.exists() else {}
    workdir = work / case_sha[:12]
    workdir.mkdir(parents=True, exist_ok=True)

    frozen_arm = sorted(FROZEN.glob(f"phase-real198/artifacts/ivanka-physical-{case_sha[:12]}-*"))
    if not frozen_arm:
        return {"case_prefix": prefix, "error": "frozen arm not found"}
    original_fasta = frozen_arm[0] / sample / "ivanka/unstitched_contigs.fasta"
    original = read_fasta(original_fasta)

    scratch_tar = CANDIDATE / "physical-cases" / case_sha / "scratch.tar.gz"
    scratch_dir = workdir / "scratch"
    if scratch_tar.exists() and not (scratch_dir / "combined_contigs.fasta").exists():
        scratch_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(scratch_tar) as tar:
            tar.extractall(scratch_dir, filter="data")
    native_files = sorted(scratch_dir.glob("assembly_*/contigs.fasta"))
    seed_files = sorted(scratch_dir.glob("assembly_*/seeds.fasta"))
    candidate = read_fasta(native_files[0]) if native_files else []
    seeds = read_fasta(seed_files[0]) if seed_files else []

    original_canon = {canonical(seq) for _, seq in original}
    candidate_canon = {canonical(seq) for _, seq in candidate}
    seed_canon = {canonical(seq) for _, seq in seeds}
    dropped = [
        {
            "len": len(seq),
            "sha256": sha(seq),
            "exact_seed_duplicate": canonical(seq) in seed_canon,
        }
        for _, seq in original
        if canonical(seq) not in candidate_canon
    ]
    added = [
        {"len": len(seq), "sha256": sha(seq)}
        for _, seq in candidate
        if canonical(seq) not in original_canon
    ]

    cand_max = max_consensus(CANDIDATE / "physical-cases" / case_sha / "conseq.csv")
    orig_max = max_consensus(frozen_arm[0] / sample / "ivanka/conseq.csv")
    rival_max: dict[str, list[dict[str, str]]] = {}
    for arm_dir in sorted(FROZEN.glob(f"phase-real198/artifacts/*-{case_sha[:12]}-*")):
        arm = arm_dir.name.split("-")[0]
        if arm == "ivanka":
            continue
        csvs = list(arm_dir.glob(f"{sample}/*/conseq.csv"))
        if csvs:
            rival_max[arm] = max_consensus(csvs[0])

    r1 = FASTQ_ROOT / sample / f"{sample}_L001_R1_001.fastq.gz"
    r2 = FASTQ_ROOT / sample / f"{sample}_L001_R2_001.fastq.gz"
    distinct: list[tuple[str, str]] = []
    seen: set[str] = set()
    sequences = (
        original
        + [(f"seed-{i}", s) for i, (_, s) in enumerate(seeds)]
        + max_sequences(orig_max, "origivanka-max")
        + max_sequences(cand_max, "candidate-max")
        + [
            row
            for arm, rows in rival_max.items()
            for row in max_sequences(rows, f"{arm}-max")
        ]
    )
    for _, seq in sequences:
        key = canonical(seq)
        if key not in seen:
            seen.add(key)
            distinct.append((key[:12], seq))
    support = coverage(distinct, r1, r2, workdir) if r1.exists() and r2.exists() else {}

    support_by_sha = {v["sha256"]: v for v in support.values()}
    dropped_support = [
        {**d, "support": support_by_sha.get(d["sha256"])} for d in dropped
    ]
    max_support = {
        label: [support_by_sha.get(row["sha256"]) for row in rows]
        for label, rows in [
            ("orig_ivanka", orig_max),
            ("candidate", cand_max),
            *rival_max.items(),
        ]
    }

    return {
        "case_sha256": case_sha,
        "case_prefix": prefix,
        "affected": entry["affected"],
        "native_g2p_duplicate_rows": entry["native_g2p_duplicate_rows"],
        "original_native_count": len(original),
        "candidate_native_count": len(candidate),
        "seed_count": len(seeds),
        "original_native": [
            {"len": len(seq), "sha256": sha(seq)} for _, seq in original
        ],
        "candidate_native": [
            {"len": len(seq), "sha256": sha(seq)} for _, seq in candidate
        ],
        "dropped_native": dropped_support,
        "added_native": added,
        "support_by_sequence": sorted(
            support.values(), key=lambda v: v["len"], reverse=True
        ),
        "original_max": [
            {k: v for k, v in row.items() if k != "sequence"} for row in orig_max
        ],
        "candidate_max": [
            {k: v for k, v in row.items() if k != "sequence"} for row in cand_max
        ],
        "max_support": max_support,
        "scores": {
            "candidate": score.get("candidate_score"),
            "original_ivanka": score.get("original_ivanka_score"),
            "original_best_rival": score.get("original_best_available_rival_score"),
            "rivals": {
                k: v.get("score")
                for k, v in score.get("original_rivals", {}).items()
                if v.get("status") == "success" and k != "ivanka"
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", required=True, help="case SHA prefix")
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument(
        "--work",
        default="/workspace/ivanka-p0-colleges-tails-20261124/research/audit-work",
        help="scratch workspace (outside all audited roots)",
    )
    args = parser.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    rows = [audit_case(prefix, work) for prefix in args.case]
    Path(args.out).write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
