"""Generate reproducible paired-end synthetic FASTQs with KNOWN genome truth.

Unlike unidentifiable-phase fixtures, every supplied genome is an explicit
generating haplotype. Truth and control FASTAs are ONLY for post-assembly
evaluation and must never be given to Ivanka as assembly seeds/references.
"""
import argparse
import gzip
import hashlib
import io
import json
import random
from pathlib import Path

DNA = "ACGT"
COMPLEMENT = str.maketrans("ACGT", "TGCA")
LENGTH = 1400
READ_LENGTH = 150
FRAGMENT_LENGTH = 260
PAIRS = 1000
CASES = {
    "clonal_exact": {"error_rate": 0.0, "minor_fraction": 0.0, "seed": 29},
    "clonal_noisy": {"error_rate": 0.003, "minor_fraction": 0.0, "seed": 31},
    "minority_phased": {"error_rate": 0.001, "minor_fraction": 0.2, "seed": 37},
    "minority_errorfree": {"error_rate": 0.0, "minor_fraction": 0.05, "seed": 41},
}


def reverse_complement(seq):
    return seq.translate(COMPLEMENT)[::-1]


def _substitute(base, rng):
    return rng.choice(DNA.replace(base, ""))


def _errors(seq, rate, rng):
    return "".join(_substitute(base, rng) if rng.random() < rate else base
                   for base in seq)


def _mutate_sites(seq, sites, rng):
    result = list(seq)
    for pos in sites:
        result[pos] = _substitute(result[pos], rng)
    return "".join(result)


def _fasta(sequences):
    return "".join(f">{name}\n{seq}\n" for name, seq in sequences)


def _gzip(path, records):
    # Explicit gzip mtime/filename for reproducible byte-for-byte fixtures.
    with path.open("xb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="ascii", newline="\n") as handle:
                for record in records:
                    handle.write(record)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_case(root, case, *, pairs=PAIRS):
    if case not in CASES:
        raise ValueError("unknown synthetic scenario")
    if pairs < 10:
        raise ValueError("at least ten pairs required")
    spec = CASES[case]
    root = Path(root) / case
    if root.exists():
        raise FileExistsError(f"refusing to overwrite {root}")
    root.mkdir(parents=True)
    rng = random.Random(spec["seed"])
    from expanded.hxb2_truth import haplotypes as source_truth
    # These older scientific smoke fixtures also obey Intent 008.
    # Full-length, real HXB2 ancestry; no purposefully targeted variants.
    major, _, _, major_proof = source_truth("clonal", spec["seed"])
    variants, _, _, minor_proof = source_truth("minority_5pct", spec["seed"])
    major, minor = major[0], variants[1]
    minor_sites = []
    genomes = [("true_major", major)]
    if spec["minor_fraction"]:
        genomes.append(("true_minor", minor))
    # Compare the same number of candidates: 'worse' contains real structural
    # errors, while 'better' reproduces the exact generating genomes.
    wrong = []
    for name, seq in genomes:
        excluded = set(minor_sites)
        candidates = [pos for pos in range(30, len(seq)-30) if pos not in excluded]
        edits = rng.sample(candidates, 18)
        wrong.append((name + "_mutated", _mutate_sites(seq, edits, rng)))
    first, second = [], []
    sources = {"true_major": 0, "true_minor": 0}
    for i in range(pairs):
        which = ("true_minor" if spec["minor_fraction"]
                 and rng.random() < spec["minor_fraction"] else "true_major")
        sources[which] += 1
        genome = minor if which == "true_minor" else major
        start = rng.randrange(len(genome) - FRAGMENT_LENGTH + 1)
        r1 = genome[start:start+READ_LENGTH]
        r2 = reverse_complement(genome[
            start+FRAGMENT_LENGTH-READ_LENGTH:start+FRAGMENT_LENGTH])
        r1 = _errors(r1, spec["error_rate"], rng)
        r2 = _errors(r2, spec["error_rate"], rng)
        name = f"truth:{case}:{i:07d}"
        first.append(f"@{name}/1\n{r1}\n+\n{'I'*READ_LENGTH}\n")
        second.append(f"@{name}/2\n{r2}\n+\n{'I'*READ_LENGTH}\n")
    paths = {
        "fastq1": root / "synthetic_R1.fastq.gz",
        "fastq2": root / "synthetic_R2.fastq.gz",
        "truth_fasta": root / "truth.fasta",
        "better_fasta": root / "better.fasta",
        "worse_fasta": root / "worse.fasta",
    }
    _gzip(paths["fastq1"], first)
    _gzip(paths["fastq2"], second)
    paths["truth_fasta"].write_text(_fasta(genomes))
    paths["better_fasta"].write_text(_fasta(genomes))
    paths["worse_fasta"].write_text(_fasta(wrong))
    manifest = {
        "schema": "ivanka.synthetic_known_truth.v1",
        "synthetic_only": True,
        "case": case,
        "seed": spec["seed"],
        "pairs": pairs,
        "read_length": READ_LENGTH,
        "fragment_length": FRAGMENT_LENGTH,
        "genome_length": len(major),
        "hxb2_ancestry": {"major": major_proof, "minor": minor_proof},
        "error_rate": spec["error_rate"],
        "minor_fraction_nominal": spec["minor_fraction"],
        "sampled_haplotype_pair_counts": sources,
        "truth_haplotype_count": len(genomes),
        "true_variant_positions": minor_sites if len(genomes) > 1 else [],
        "known_truth": True,
        "higher_truth_alignment_expected": "better.fasta > worse.fasta",
        "truth_is_evaluation_only": True,
        "clinical_qualification_effect": "none",
        "files_sha256": {name: _digest(path) for name, path in paths.items()},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--pairs", type=int, default=PAIRS)
    p.add_argument("--case", choices=tuple(CASES), action="append")
    args = p.parse_args(argv)
    scenarios = args.case or list(CASES)
    results = [generate_case(args.output_dir, case, pairs=args.pairs)
               for case in scenarios]
    print(json.dumps([{"case": x["case"], "pairs": x["pairs"],
                       "hashes": x["files_sha256"]} for x in results], indent=2))


if __name__ == "__main__":
    main()
