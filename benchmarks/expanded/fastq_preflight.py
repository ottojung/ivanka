"""MiCall-compatible Illumina paired FASTQ validation, before container launch."""
import gzip
from itertools import zip_longest
import re

HEADER = re.compile(r"^@([^\s]+) ([12]):([YN]):([0-9]+):([^\s]+)$")
BASES = frozenset("ACGTN")


def records(path):
    with gzip.open(path, "rt", encoding="ascii", newline="") as stream:
        while True:
            header = stream.readline()
            if not header:
                return
            seq, plus, qual = [stream.readline() for _ in range(3)]
            if not seq or not plus or not qual:
                raise ValueError("truncated FASTQ record")
            sequence, quality = seq.rstrip("\r\n"), qual.rstrip("\r\n")
            if not plus.startswith("+") or not sequence or len(sequence) != len(quality):
                raise ValueError("invalid FASTQ separator, sequence, or quality")
            if set(sequence.upper()) - BASES:
                raise ValueError("invalid nucleotide in synthetic paired FASTQ")
            match = HEADER.fullmatch(header.rstrip("\r\n"))
            if match is None:
                raise ValueError("MiCall requires a CASAVA-style paired FASTQ header")
            yield match.group(1), int(match.group(2))


def verify_pairs(first, second, expected):
    if not isinstance(expected, int) or expected < 1:
        raise ValueError("invalid expected original read pair count")
    total = 0
    for a, b in zip_longest(records(first), records(second)):
        if a is None or b is None:
            raise ValueError("unequal FASTQ mate record counts")
        if a[0] != b[0] or a[1] != 1 or b[1] != 2:
            raise ValueError("invalid FASTQ mate ID or CASAVA read number")
        total += 1
    if total != expected:
        raise ValueError(f"FASTQ pair count {total} != manifest {expected}")
    return total
