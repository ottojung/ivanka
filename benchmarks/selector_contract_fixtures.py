"""Synthetic paired-read fixtures with stable and reproducible fragments."""
import gzip
from pathlib import Path
import random


def sample_reads(folder, *, count=40, reverse=False, zipped=False, seed=901):
    rng = random.Random(seed)
    template = "".join(rng.choices("ACGT", k=260))
    path1, path2 = (Path(folder)/"R1.fastq", Path(folder)/"R2.fastq")
    records = ([], [])
    for n in range(count):
        begin = (n*11+3) % 140
        first = template[begin:begin+90]
        second = template[begin+25:begin+115]
        if reverse:
            first, second = second, first
        for mate, sequence in enumerate((first, second)):
            records[mate].append(f"@pair-{n}\n{sequence}\n+\n{'I'*len(sequence)}\n")
    for path, content in zip((path1, path2), records):
        path.write_text("".join(content))
    if zipped:
        paths = []
        for path in (path1, path2):
            gz = path.with_suffix(path.suffix+".gz")
            with gzip.open(gz, "wt") as stream:
                stream.write(path.read_text())
            paths.append(gz)
        return template, tuple(paths)
    return template, (path1, path2)
