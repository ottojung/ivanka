"""Deterministic, heterogeneous synthetic viral paired-read experiments.

Every genome is independently synthesized, never a known reference.
Only reads/ is accessible to assemblers; hidden-truth/ is scorer-only.
"""
import argparse
import gzip
import hashlib
import io
import json
import random
from pathlib import Path

DNA = "ACGT"
COMP = str.maketrans("ACGT", "TGCA")
READ_LENGTH = 150
FRAGMENT = 270
# 25 experimental families x 16 seeds = 400 synthetic samples by default.
FAMILIES = (
    "clonal", "iid_errors", "quality_decay", "cycle_bursts",
    "homopolymer_slippage", "systematic_errors", "gc_dropout",
    "amplicon_hotspots", "coverage_hole", "low_depth", "ultradeep",
    "pcr_jackpot", "mate_quality_asymmetry", "strand_bias", "adapter_tails",
    "contaminated", "minority_5pct", "minority_30pct", "equal_strains",
    "tandem_repeat", "inverted_repeat", "overlapping_mates",
    "long_inserts", "discordant_pairs", "complex_mixture",
)


def rc(sequence):
    return sequence.translate(COMP)[::-1]


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_alt(base, rng):
    return rng.choice(DNA.replace(base, ""))


def template(rng, family, length=2600):
    seq = "".join(rng.choices(DNA, k=length))
    if family == "gc_dropout":
        seq = ("".join(rng.choices("AT", k=950)) +
               "".join(rng.choices("GC", k=950)) +
               "".join(rng.choices(DNA, k=length-1900)))
    if family == "homopolymer_slippage":
        seq = seq[:840] + "A" * 56 + seq[896:1450] + "G" * 48 + seq[1498:]
    if family == "tandem_repeat":
        seq = seq[:1050] + seq[540:860] + seq[1050:]
    if family == "inverted_repeat":
        seq = seq[:1340] + rc(seq[350:670]) + seq[1340:]
    return seq


def haplotypes(rng, family):
    dominant = template(rng, family)
    if family not in ("minority_5pct", "minority_30pct", "equal_strains",
                      "complex_mixture"):
        return [dominant], [1.0]
    variants = [dominant]
    for i in range(1, 4 if family == "complex_mixture" else 2):
        bases = list(dominant)
        for _ in range(13 if family == "complex_mixture" else 8):
            position = rng.randrange(60, len(bases)-60)
            bases[position] = pick_alt(bases[position], rng)
        variants.append("".join(bases))
    if family == "minority_5pct":
        return variants, [0.95, 0.05]
    if family == "minority_30pct":
        return variants, [0.7, 0.3]
    if family == "equal_strains":
        return variants, [0.5, 0.5]
    return variants, [0.65, 0.25, 0.08, 0.02]


def read_errors(sequence, family, rng, *, mate, start):
    """Sequencing errors: correlated cycles, context, indels and bad mate."""
    bases = list(sequence)
    for i, base in enumerate(bases):
        probability = 0.0 if family == "clonal" else 0.0004
        if family == "iid_errors":
            probability = 0.006
        if family == "quality_decay" and i > 90:
            probability += 0.09 * (i-90)/max(1, len(bases)-90)
        if family == "cycle_bursts" and 65 <= i < 78:
            probability = 0.15
        if family == "mate_quality_asymmetry" and mate == 2:
            probability = 0.045
        if family == "systematic_errors" and (start+i) % 193 == 71:
            probability = 0.82
        if rng.random() < probability:
            bases[i] = pick_alt(base, rng)
    if family == "homopolymer_slippage":
        sites = [i for i in range(4, len(bases)-2)
                 if len(set(bases[i-4:i+2])) == 1]
        if sites and rng.random() < 0.16:
            at = rng.choice(sites)
            if rng.random() < 0.5:
                bases.pop(at)
                bases.append(rng.choice(DNA))
            else:
                bases.insert(at, bases[at])
                bases.pop()
    quality = ["I"] * len(bases)
    if family == "quality_decay":
        for i in range(90, len(quality)):
            quality[i] = chr(33 + max(8, 39 - (i-90)//2))
    if family == "cycle_bursts":
        for i in range(65, min(78, len(quality))):
            quality[i] = "0"
    if family == "mate_quality_asymmetry" and mate == 2:
        quality = ["5"] * len(bases)
    return "".join(bases), "".join(quality)


def choose_fragment(rng, genome, family, *, reusable):
    insert = (185 if family == "overlapping_mates" else
              rng.randrange(500, 641) if family == "long_inserts" else FRAGMENT)
    if family == "pcr_jackpot":
        # Repeated independent reads from one of just 13 original fragments.
        # The fixed pool stores (start, insert), in that order.
        return rng.choice(reusable)
    width = len(genome) - insert + 1
    if width < 1:
        raise ValueError("fragment longer than haplotype")
    for _ in range(300):
        if family == "amplicon_hotspots":
            centers = [int(len(genome)*fraction) for fraction in (0.18, 0.48, 0.78)]
            start = max(0, min(width-1, rng.choice(centers) + rng.gauss(0, 90)))
            start = int(start)
        else:
            start = rng.randrange(width)
        if family == "coverage_hole":
            # Hard interval with no fragment evidence, not merely low coverage.
            hole = (int(len(genome)*0.43), int(len(genome)*0.54))
            if start < hole[1] and start+insert > hole[0]:
                continue
        if family == "gc_dropout":
            gc = (genome[start:start+insert].count("G")
                  + genome[start:start+insert].count("C")) / insert
            if rng.random() > max(0.04, 1-5*abs(gc-0.46)):
                continue
        return start, insert
    # Fixed RNG and bounded sampling, without silently relaxing a hole.
    raise ValueError("could not sample a valid fragment")


def _write_gzip(path, records):
    with path.open("xb") as handle:
        with gzip.GzipFile(fileobj=handle, filename="", mode="wb", mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="ascii", newline="\n") as output:
                output.writelines(records)


def generate_case(root, family, seed, pairs=900):
    if family not in FAMILIES or not isinstance(seed, int) or seed < 0:
        raise ValueError("invalid synthetic case")
    if pairs < 20:
        raise ValueError("at least 20 pairs required")
    case = Path(root) / f"{family}-s{seed:03d}"
    if case.exists():
        raise FileExistsError(f"refusing to overwrite {case}")
    read_dir = case / "reads"
    truth_dir = case / "hidden-truth"
    read_dir.mkdir(parents=True)
    truth_dir.mkdir()
    rng = random.Random(int.from_bytes(
        hashlib.sha256(f"expanded-v1:{family}:{seed}".encode()).digest()[:8], "big"))
    genomes, fractions = haplotypes(rng, family)
    decoy = template(rng, "clonal")
    reusable = [(rng.randrange(len(genomes[0])-FRAGMENT+1), FRAGMENT)
                for _ in range(13)] if family == "pcr_jackpot" else []
    total = max(20, pairs//4) if family == "low_depth" else (
        3*pairs if family == "ultradeep" else pairs)
    first, second = [], []
    counts = [0] * len(genomes)
    starts = set()
    contaminants = chimeras = 0
    for i in range(total):
        index = rng.choices(range(len(genomes)), weights=fractions)[0]
        counts[index] += 1
        genome = genomes[index]
        contaminated = family == "contaminated" and rng.random() < 0.035
        if contaminated:
            genome = decoy
            contaminants += 1
        start, insert = choose_fragment(rng, genome, family, reusable=reusable)
        starts.add((start, insert, index))
        r1 = genome[start:start+READ_LENGTH]
        r2 = rc(genome[start+insert-READ_LENGTH:start+insert])
        if rng.random() < (0.08 if family == "strand_bias" else 0.5):
            # Ordinary paired-end fragments are sampled from both strands.
            # The biased library has only 8% reverse-strand fragment starts.
            r1, r2 = r2, r1
        if family == "discordant_pairs" and rng.random() < 0.08:
            new_start = rng.randrange(len(genome)-READ_LENGTH+1)
            r2 = rc(genome[new_start:new_start+READ_LENGTH])
            chimeras += 1
        r1, q1 = read_errors(r1, family, rng, mate=1, start=start)
        r2, q2 = read_errors(r2, family, rng, mate=2,
                             start=start+insert-READ_LENGTH)
        if family == "adapter_tails":
            # A shared technical tail can falsely join unrelated templates.
            r1, r2 = r1[:-18] + "AGATCGGAAGAGCACACG", r2[:-18] + "AGATCGGAAGAGCACACG"
        name = f"synthetic:{family}:{seed}:{i:08d}"
        first.append(f"@{name}/1\n{r1}\n+\n{q1}\n")
        second.append(f"@{name}/2\n{r2}\n+\n{q2}\n")
    fq1, fq2 = read_dir / "R1.fastq.gz", read_dir / "R2.fastq.gz"
    truth = truth_dir / "haplotypes.fasta"
    _write_gzip(fq1, first)
    _write_gzip(fq2, second)
    truth.write_text("".join(
        f">haplotype_{i+1}\n{genome}\n" for i, genome in enumerate(genomes)))
    data = {
        "schema": "ivanka.expanded.synthetic.v1", "family": family, "seed": seed,
        "pairs": total, "read_length": READ_LENGTH, "haplotype_count": len(genomes),
        "nominal_fractions": fractions, "sampled_haplotype_pairs": counts,
        "unique_fragment_coordinates": len(starts), "chimeric_mates": chimeras,
        "contamination_pairs": contaminants, "truth_is_evaluation_only": True,
        "read_files": ["reads/R1.fastq.gz", "reads/R2.fastq.gz"],
        "hidden_truth_file": "hidden-truth/haplotypes.fasta",
        "sha256": {str(path.relative_to(case)): fingerprint(path)
                   for path in (fq1, fq2, truth)},
    }
    (case / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True)+"\n")
    return data


def generate_cohort(root, seeds=16, pairs=900):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"refusing nonempty cohort {root}")
    root.mkdir(parents=True, exist_ok=True)
    records = [generate_case(root, family, seed, pairs)
               for family in FAMILIES for seed in range(seeds)]
    manifest = {"schema": "ivanka.expanded.cohort.v1", "families": list(FAMILIES),
                "seeds_per_family": seeds, "samples": len(records),
                "cases": [{"id": f"{x['family']}-s{x['seed']:03d}",
                           "sha256": x["sha256"]} for x in records]}
    with (root / "cohort.json").open("x") as out:
        json.dump(manifest, out, indent=2, sort_keys=True)
        out.write("\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--seeds", type=int, default=16)
    parser.add_argument("--pairs", type=int, default=900)
    args = parser.parse_args()
    if not (1 <= args.seeds <= 128):
        parser.error("--seeds must be 1..128")
    cohort = generate_cohort(args.out, args.seeds, args.pairs)
    print(json.dumps({"samples": cohort["samples"],
                      "families": len(cohort["families"])}, sort_keys=True))


if __name__ == "__main__":
    main()
