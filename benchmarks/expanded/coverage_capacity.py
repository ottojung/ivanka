"""Read-only diagnostic of MiCall's depth floor for synthetic DNA cases."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .score import read_fasta

SCHEMA = "ivanka.expanded.coverage_capacity.v1"


def threshold(micall):
    source = Path(micall) / "micall/core/aln2counts.py"
    raw = source.read_bytes()
    matches = re.findall(rb"(?m)^CONSENSUS_MIN_COVERAGE = ([0-9]+)\s*$", raw)
    if len(matches) != 1 or int(matches[0]) < 1:
        raise ValueError("MiCall consensus depth threshold is ambiguous")
    return int(matches[0]), hashlib.sha256(raw).hexdigest()


def one_case(folder, minimum):
    manifest_raw = (folder / "manifest.json").read_bytes()
    record = json.loads(manifest_raw)
    truth_name = record["hidden_truth_file"]
    if (Path(truth_name).is_absolute()
            or ".." in Path(truth_name).parts):
        raise ValueError("truth path escapes synthetic case")
    truth_file = folder / truth_name
    digest = hashlib.sha256(truth_file.read_bytes()).hexdigest()
    if record["sha256"][truth_name] != digest:
        raise ValueError("synthetic truth digest mismatch")
    verified_reads = {}
    for name in ("reads/R1.fastq.gz", "reads/R2.fastq.gz"):
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if record["sha256"][name] != actual:
            raise ValueError("synthetic reads digest mismatch")
        verified_reads[name] = actual
    fraction = record["nominal_fractions"]
    truth = read_fasta(truth_file)
    if len(truth) != len(fraction) or not truth:
        raise ValueError("invalid synthetic dominant truth")
    chosen = max(range(len(truth)), key=lambda i: fraction[i])
    pairs, read_len = record["pairs"], record["read_length"]
    length = len(truth[chosen])
    if (type(pairs) is not int or type(read_len) is not int
            or pairs < 0 or read_len < 1 or length < 1):
        raise ValueError("invalid read length or pair count")
    ceiling = pairs * 2 * read_len / length
    return {"case": folder.name, "family": record["family"],
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "read_sha256": verified_reads,
            "pairs": pairs, "read_length": read_len,
            "dominant_truth_length": length,
            "all_reads_mean_depth_ceiling": round(ceiling, 6),
            "below_global_depth_floor": pairs * 2 * read_len < length * minimum}


def audit(cohort, micall):
    minimum, source_hash = threshold(micall)
    root = Path(cohort)
    cases = [one_case(folder, minimum)
             for folder in sorted(root.iterdir())
             if (folder / "manifest.json").is_file()]
    if not cases:
        raise ValueError("no synthetic cases discovered")
    from collections import Counter
    all_families = Counter(row["family"] for row in cases)
    below = Counter(row["family"] for row in cases
                    if row["below_global_depth_floor"])
    return {"schema": SCHEMA, "qualification": "NOT_EVALUATED",
            "miCall_consensus_min_coverage": minimum,
            "miCall_aln2counts_sha256": source_hash,
            "cases": cases, "case_count": len(cases),
            "families": {name: {"cases": count, "below_floor": below[name]}
                         for name, count in sorted(all_families.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--micall", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(audit(args.cohort, args.micall),
                      sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
