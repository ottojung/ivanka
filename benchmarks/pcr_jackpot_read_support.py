"""Post-assembly PCR-jackpot diagnostic; never used as an assembly input."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from contig_diversity import _fastq_sequences, canonical_kmers, read_fasta

K = 31
CASES = {f"pcr_jackpot-s{i:03d}" for i in range(16)}
RIVALS = {"iva", "haploflow", "megahit", "abyss", "spades", "velvet"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contigs(path):
    with path.open() as stream:
        return set().union(*(canonical_kmers(row["contig"].upper(), K)
                             for row in csv.DictReader(stream)))


def read_support(paths, truth):
    reads = set()
    counts = []
    for path in paths:
        n = 0
        for seq in _fastq_sequences(path, max_records=2**63 - 1):
            reads.add(seq)
            n += 1
        counts.append(n)
    if len(counts) != 2 or not counts[0] or counts[0] != counts[1]:
        raise ValueError("nonempty matched read files required")
    support = Counter()
    for seq in reads:
        support.update(canonical_kmers(seq, K) & truth)
    return support


def compare(truth, support, candidate, rival):
    observed = set(support) & truth
    if not observed:
        raise ValueError("no exact truth k-mers observed")
    missing = (rival - candidate) & observed
    return {
        "truth_kmers_in_reads": len(observed),
        "candidate_raw_supported": len(candidate & observed),
        "rival_raw_supported": len(rival & observed),
        "rival_only_supported_by_reads": len(missing),
        "rival_only_supported_by_3_distinct_read_strings":
            sum(support[k] >= 3 for k in missing),
    }


def evaluate(candidate_root, frozen_root, data_root):
    results = candidate_root / "results.jsonl"
    rows = {}
    for line in results.read_text().splitlines():
        row = json.loads(line)
        if row["family"] != "pcr_jackpot":
            continue
        case = row["id"]
        if case not in CASES or case in rows:
            raise ValueError("unexpected or duplicate PCR-jackpot case")
        rows[case] = row["results"]
    if set(rows) != CASES:
        raise ValueError("incomplete PCR-jackpot cohort")
    output = []
    for case, arms in sorted(rows.items()):
        if arms["ivanka"]["status"] != "success":
            raise ValueError(f"{case}: candidate not successful")
        rivals = {k: v for k, v in arms.items()
                  if k in RIVALS and v["status"] == "success"}
        if not rivals:
            raise ValueError(f"{case}: no successful rival")
        best = max(sorted(rivals), key=lambda k: rivals[k]["score"])
        score = arms["ivanka"]["score"]
        rival_score = rivals[best]["score"]
        if not all(math.isfinite(x) for x in (score, rival_score)) or rival_score <= 0:
            raise ValueError(f"{case}: invalid scores")
        data = data_root / case
        truth_path = data / "hidden-truth/haplotypes.fasta"
        sequences = read_fasta(truth_path)
        if len(sequences) != 1:
            raise ValueError(f"{case}: expected one truth")
        truth = canonical_kmers(sequences[0], K)
        r1, r2 = (data / "reads" / f"R{i}.fastq.gz" for i in (1, 2))
        candidate_path = candidate_root / case / "unstitched_contigs.csv"
        rival_path = frozen_root / case / best / "unstitched_contigs.csv"
        support = read_support([r1, r2], truth)
        output.append({
            "case": case, "best_rival": best,
            "candidate_score": score, "rival_score": rival_score,
            "relative_floor_miss": score < 0.9 * rival_score,
            "input_sha256": {name: digest(path) for name, path in
                             (("truth", truth_path), ("r1", r1), ("r2", r2),
                              ("candidate_contigs", candidate_path),
                              ("rival_contigs", rival_path))},
            **compare(truth, support, contigs(candidate_path), contigs(rival_path)),
        })
    misses = [x for x in output if x["relative_floor_miss"]]
    return {
        "schema": "pcr-jackpot-read-support-diagnostic-v1",
        "k": K, "results_sha256": digest(results),
        "not_qualification": True,
        "relative_floor_misses": len(misses),
        "median_candidate_recovery_on_misses": statistics.median(
            x["candidate_raw_supported"] / x["truth_kmers_in_reads"] for x in misses
        ) if misses else None,
        "median_rival_recovery_on_misses": statistics.median(
            x["rival_raw_supported"] / x["truth_kmers_in_reads"] for x in misses
        ) if misses else None,
        "cases": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-root", "frozen-root", "data-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.candidate_root, args.frozen_root, args.data_root)
    # Exclusive creation prevents replacing any existing evidence.
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
