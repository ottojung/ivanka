"""Retrospective unphased evidence diagnostic for failing abundant truths."""
import argparse
import json
from pathlib import Path
import statistics

from contig_diversity import canonical_kmers, read_fasta
from pcr_jackpot_read_support import contigs, digest, read_support


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
        own = arms["ivanka"]
        if own["status"] != "success":
            raise ValueError("candidate not successful")
        truth_path = data / case / "hidden-truth/haplotypes.fasta"
        truths = read_fasta(truth_path)
        if len(truths) != 2:
            raise ValueError("expected two truth sequences")
        kmers = [canonical_kmers(t, 31) for t in truths]
        mates = [data / case / "reads" / f"R{i}.fastq.gz" for i in (1, 2)]
        support = set(read_support(mates, kmers[0] | kmers[1]))
        candidate_path = candidate / case / "unstitched_contigs.csv"
        raw = contigs(candidate_path)
        for i in (0, 1):
            key = f"truth_{i}"
            rivals = {a: b for a, b in arms.items() if a != "ivanka"
                      and b["status"] == "success" and key in b.get("per_truth", {})}
            best = max(sorted(rivals), key=lambda a: rivals[a]["per_truth"][key]["fraction"])
            fraction = own["per_truth"][key]["fraction"]
            strongest = rivals[best]["per_truth"][key]["fraction"]
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
