"""Deterministic pairwise-to-HXB2-coordinate multiple alignment builder.

Reference inputs are public, source-pinned GenBank records. Only the
benchmark generator/evaluator consumes these; no assembled candidate does.
"""
import zlib  # noqa: F401  # Ensure NumPy import works under Guix profiles.
from Bio import SeqIO
from Bio.Align import PairwiseAligner
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCESSIONS = ("K03455.1", "U46016.1", "MH705157.1")


def read_seq(name):
    record = next(SeqIO.parse(HERE / f"{name}.fasta", "fasta"))
    if not record.id.startswith(name) or set(str(record.seq)) - set("ACGT"):
        raise ValueError("invalid pinned biological reference " + name)
    return str(record.seq)


def pairwise_projection(reference, other):
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -7
    aligner.extend_gap_score = -1
    aligned = aligner.align(reference, other)[0]
    head, tail = str(aligned[0]), str(aligned[1])
    insertions = [""] * (len(reference) + 1)
    aligned_bases = ["-"] * len(reference)
    position = 0
    for original, alternative in zip(head, tail):
        if original == "-":
            insertions[position] += alternative
        else:
            aligned_bases[position] = alternative
            position += 1
    if position != len(reference):
        raise ValueError("reference alignment not fully anchored")
    assert "".join(insertions) + "".join(aligned_bases) != ""
    return insertions, aligned_bases


def alignment():
    ref = read_seq(ACCESSIONS[0])
    projections = {name: pairwise_projection(ref, read_seq(name))
                   for name in ACCESSIONS[1:]}
    columns = {name: [] for name in ACCESSIONS}
    for position in range(len(ref) + 1):
        gap_count = max(len(value[0][position]) for value in projections.values())
        columns[ACCESSIONS[0]].append("-" * gap_count)
        for name, (insertions, _) in projections.items():
            columns[name].append(insertions[position].ljust(gap_count, "-"))
        if position < len(ref):
            columns[ACCESSIONS[0]].append(ref[position])
            for name, (_, bases) in projections.items():
                columns[name].append(bases[position])
    records = {name: "".join(columns[name]) for name in ACCESSIONS}
    if (len(set(map(len, records.values()))) != 1
            or any(records[name].replace("-", "") != read_seq(name)
                   for name in ACCESSIONS)):
        raise ValueError("multiple reference alignment changed pinned sequences")
    return records


def main():
    records = alignment()
    out = HERE / "hxb2-subtypes-aligned.fasta"
    with out.open("x") as file:
        for name, sequence in records.items():
            file.write(f">{name}\n")
            for start in range(0, len(sequence), 80):
                file.write(sequence[start:start+80] + "\n")
    print("HXB2_ALIGNMENT", len(next(iter(records.values()))),
          {name: sequence.count("-") for name, sequence in records.items()})


if __name__ == "__main__":
    main()
