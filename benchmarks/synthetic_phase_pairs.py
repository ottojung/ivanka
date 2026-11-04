#!/usr/bin/env python3
"""Deterministic paired FASTQ with two observationally ambiguous phase truths.

No real data, alignment, MiCall, reference mapping or molecule duplication.
Provides a synthetic negative control for unsupported long-range phasing.
"""
import argparse
import gzip
import io
import json
import random
from pathlib import Path

DNA = "ACGT"
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def observed(position, start, read_length, fragment_length):
    return (start <= position < start + read_length
            or start + fragment_length - read_length <= position
            < start + fragment_length)


def variant_truths(length, positions, randomizer):
    ancestor = "".join(randomizer.choice(DNA) for _ in range(length))
    alternatives = tuple(DNA[(DNA.index(ancestor[pos]) + 1) % 4]
                         for pos in positions)

    def with_variants(variant_indices):
        bases = list(ancestor)
        for index in variant_indices:
            bases[positions[index]] = alternatives[index]
        return "".join(bases)

    return ((ancestor, with_variants((0, 1))),
            (with_variants((1,)), with_variants((0,))),
            alternatives)


def mutated(sequence, rate, randomizer):
    if rate == 0:
        return sequence
    output = []
    for base in sequence:
        if randomizer.random() < rate:
            output.append(randomizer.choice(DNA.replace(base, "")))
        else:
            output.append(base)
    return "".join(output)


def paired_reads(haplotype, start, read_length, fragment_length):
    first = haplotype[start:start + read_length]
    last = haplotype[start + fragment_length - read_length:start + fragment_length]
    return first, reverse_complement(last)


def write_gzip(path, records):
    with path.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, filename="", mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="ascii", newline="\n") as stream:
                stream.write("".join(records))


def generate(directory, length=1400, read_length=100, fragment_length=300,
             pairs_per_haplotype=500, variants=(280, 900), seed=17,
             error_rate=0.0):
    positions = tuple(variants)
    if (length < 2 or not 0 < read_length <= fragment_length <= length
            or pairs_per_haplotype < 1 or len(positions) != 2
            or not all(type(pos) is int and 0 <= pos < length
                       for pos in positions)
            or positions[0] >= positions[1]
            or not 0 <= error_rate < 1):
        raise ValueError("Invalid synthetic paired-read geometry or error rate")
    randomizer = random.Random(seed)
    coupled, decoupled, alleles = variant_truths(length, positions, randomizer)
    first_fastq, second_fastq = [], []
    bridges = 0
    alternative_explains = True
    alternate_hap_counts = [0, 0]
    for i in range(2 * pairs_per_haplotype):
        which = i % 2
        start = randomizer.randrange(length - fragment_length + 1)
        seeing = tuple(observed(pos, start, read_length, fragment_length)
                       for pos in positions)
        bridges += int(all(seeing))
        alternative_hap = which ^ int(seeing[1])
        alternate_hap_counts[alternative_hap] += 1
        unaltered = paired_reads(coupled[which], start, read_length,
                                fragment_length)
        alternative = paired_reads(decoupled[alternative_hap], start,
                                   read_length, fragment_length)
        alternative_explains &= unaltered == alternative
        mate1, mate2 = (mutated(seq, error_rate, randomizer)
                        for seq in unaltered)
        qname = f"synthetic:{seed}:{i:07d}"
        first_fastq.append(f"@{qname} 1:N:0:0\n{mate1}\n+\n{'I'*read_length}\n")
        second_fastq.append(f"@{qname} 2:N:0:0\n{mate2}\n+\n{'I'*read_length}\n")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = [directory / name for name in
               ("synthetic_R1.fastq.gz", "synthetic_R2.fastq.gz", "truth.json")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("Synthetic outputs already exist; refusing overwrite")
    write_gzip(directory / "synthetic_R1.fastq.gz", first_fastq)
    write_gzip(directory / "synthetic_R2.fastq.gz", second_fastq)
    truth = {
        "synthetic_only": True,
        "length": length,
        "read_length": read_length,
        "fragment_length": fragment_length,
        "pairs_per_haplotype": pairs_per_haplotype,
        "original_qname_pairs": 2 * pairs_per_haplotype,
        "variant_positions_zero_based": list(positions),
        "alternate_bases": list(alleles),
        "sequencing_error_rate": error_rate,
        "seed": seed,
        "phase_coupled_haplotypes": list(coupled),
        "phase_decoupled_haplotypes": list(decoupled),
        "read_pairs_directly_observing_both_variants": bridges,
        "decoupled_latent_haplotype_pair_counts": alternate_hap_counts,
        "alternative_phase_explains_identical_original_reads":
            alternative_explains,
        "interpretation": (
            "If no original pair observes both variants, opposite long-range "
            "phase assignments can explain exactly the same paired-end "
            "sequences. This does not prove which haplotypes are biological. "
            "Read identities are unique and never duplicated."),
    }
    (directory / "truth.json").write_text(json.dumps(truth, indent=2) + "\n")
    return truth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--length", type=int, default=1400)
    parser.add_argument("--read-length", type=int, default=100)
    parser.add_argument("--fragment-length", type=int, default=300)
    parser.add_argument("--pairs-per-haplotype", type=int, default=500)
    parser.add_argument("--variants", type=int, nargs=2, default=(280, 900))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--error-rate", type=float, default=0.0)
    args = parser.parse_args()
    result = generate(args.output_dir, args.length, args.read_length,
                      args.fragment_length, args.pairs_per_haplotype,
                      args.variants, args.seed, args.error_rate)
    print(json.dumps({k: result[k] for k in (
        "original_qname_pairs", "read_pairs_directly_observing_both_variants",
        "alternative_phase_explains_identical_original_reads")}, indent=2))


if __name__ == "__main__":
    main()
