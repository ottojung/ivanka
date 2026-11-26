"""Retrospective unphased evidence diagnostic for failing abundant truths."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from contig_diversity import canonical_kmers, read_fasta
from pcr_jackpot_read_support import RIVALS, contigs, digest, read_support


def validate_panel(arm, truths):
    """Bind every successful per-truth measurement to the exact FASTA identity."""
    panel = arm.get("per_truth")
    if not isinstance(panel, dict) or set(panel) != {"truth_0", "truth_1"}:
        raise ValueError("missing or unexpected equal-strain truth panel")
    for i, seq in enumerate(truths):
        record = panel[f"truth_{i}"]
        if (not isinstance(record, dict)
                or record.get("truth_sha256") != hashlib.sha256(seq.encode()).hexdigest()
                or record.get("length") != len(seq)
                or record.get("nominal_abundance") != 0.5):
            raise ValueError("equal-strain truth identity mismatch")
        fraction = record.get("fraction")
        score = record.get("score")
        if (any(isinstance(x, bool) or not isinstance(x, (int, float))
                or not math.isfinite(x) for x in (fraction, score))
                or not 0 <= fraction <= 1
                or not math.isclose(fraction, score / len(seq), abs_tol=1e-9)):
            raise ValueError("invalid equal-strain truth fraction")
    return panel


def evaluate(candidate, frozen, data):
    rows = []
    seen = set()
    ledger = candidate / "results.jsonl"
    for line in ledger.read_text().splitlines():
        row = json.loads(line)
        if row["family"] != "equal_strains":
            continue
        case = row["id"]
        if case in seen or case not in {f"equal_strains-s{i:03d}" for i in range(16)}:
            raise ValueError("duplicate or unexpected case")
        seen.add(case)
        arms = row["results"]
        if set(arms) != RIVALS | {"ivanka"}:
            raise ValueError("wrong assembler roster")
        own = arms["ivanka"]
        if own["status"] != "success":
            raise ValueError("candidate not successful")
        truth_path = data / case / "hidden-truth/haplotypes.fasta"
        truths = read_fasta(truth_path)
        if len(truths) != 2:
            raise ValueError("expected two truth sequences")
        if any(not t for t in truths):
            raise ValueError("empty truth sequence")
        panels = {a: validate_panel(b, truths) for a, b in arms.items()
                  if b["status"] == "success"}
        rivals = {a: b for a, b in panels.items() if a != "ivanka"}
        if not rivals:
            raise ValueError("no successful rival")
        kmers = [canonical_kmers(t, 31) for t in truths]
        mates = [data / case / "reads" / f"R{i}.fastq.gz" for i in (1, 2)]
        support = set(read_support(mates, kmers[0] | kmers[1]))
        candidate_path = candidate / case / "unstitched_contigs.csv"
        raw = contigs(candidate_path)
        for i in (0, 1):
            key = f"truth_{i}"
            best = max(sorted(rivals), key=lambda a: rivals[a][key]["fraction"])
            fraction = panels["ivanka"][key]["fraction"]
            strongest = rivals[best][key]["fraction"]
            if fraction + 1e-7 >= 0.9 * strongest:
                continue
            observed = (kmers[i] - kmers[1 - i]) & support
            if not observed:
                raise ValueError("no observed exclusive truth k-mers")
            rival_path = frozen / case / best / "unstitched_contigs.csv"
            rows.append({
                "case": case, "truth": key, "best_rival": best,
                "candidate_final_fraction": fraction, "best_final_fraction": strongest,
                "read_observed_exclusive_truth_kmers": len(observed),
                "candidate_raw_exclusive_recovered": len(raw & observed),
                "best_raw_exclusive_recovered": len(contigs(rival_path) & observed),
                "input_sha256": {k: digest(p) for k, p in zip(
                    ("truth", "r1", "r2", "candidate", "rival"),
                    (truth_path, *mates, candidate_path, rival_path), strict=True)},
            })
    if len(seen) != 16:
        raise ValueError("incomplete equal-strains cohort")
    medians = {name: statistics.median(
        r[name] / r["read_observed_exclusive_truth_kmers"] for r in rows)
        if rows else None for name in ("candidate_raw_exclusive_recovered", "best_raw_exclusive_recovered")}
    return {"schema": "posthoc-only-equal-strains-exclusive-read-support-v1",
            "k": 31, "not_qualification": True, "results_sha256": digest(ledger),
            "failing_truth_count": len(rows), "failing_case_count": len({r["case"] for r in rows}),
            "medians": medians, "cases": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-root", "frozen-root", "data-root", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    report = evaluate(a.candidate_root, a.frozen_root, a.data_root)
    with a.output.open("x") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
