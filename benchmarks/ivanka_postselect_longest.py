#!/usr/bin/env python3
"""Experiment: keep the longest N of Ivanka's *fully assembled* contigs.

The native Ivanka binary runs unchanged with its normal multi-seed search;
only its emitted FASTA is post-selected. MiCall and IVA remain unchanged.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ORIGINAL = "/usr/local/bin/ivanka-native"


def output_path(arguments):
    candidates = []
    for i, a in enumerate(arguments):
        if a == "--output" and i + 1 < len(arguments):
            candidates.append(arguments[i+1])
        elif a.startswith("--output="):
            candidates.append(a.partition("=")[2])
    if len(candidates) != 1 or not candidates[0]:
        raise ValueError("Expected one --output FASTA argument")
    return Path(candidates[0])


def parse_fasta(path):
    entries = []
    header, parts = None, []
    with Path(path).open(encoding="ascii") as stream:
        for line in stream:
            line = line.rstrip("\n\r")
            if line.startswith(">"):
                if header is not None:
                    entries.append((header, "".join(parts)))
                header, parts = line, []
            elif line.strip():
                if header is None:
                    raise ValueError("FASTA sequence without header")
                parts.append(line.strip())
    if header is not None:
        entries.append((header, "".join(parts)))
    if not entries or any(not seq for _, seq in entries):
        raise ValueError("No nonempty native Ivanka FASTA contigs")
    return entries


def top_contigs(entries, limit):
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid post-selection limit")
    # Stable tie-break uses original native emitter order, not patient metadata.
    order = sorted(range(len(entries)), key=lambda i: (-len(entries[i][1]), i))
    return [entries[i] for i in order[:limit]]


def replace_fasta(path, entries):
    path = Path(path)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii",
                prefix=".ivanka-ranked-", suffix=".fasta", dir=path.parent,
                delete=False) as dest:
            tmp = Path(dest.name)
            for header, sequence in entries:
                dest.write(header + "\n")
                for i in range(0, len(sequence), 80):
                    dest.write(sequence[i:i+80] + "\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def main(arguments):
    limit = int(os.environ.get("IVANKA_POSTSELECT_CONTIGS", "1"))
    if not 1 <= limit <= 1000:
        raise ValueError("IVANKA_POSTSELECT_CONTIGS must be within 1..1000")
    target = output_path(arguments)
    subprocess.run([ORIGINAL, *arguments], check=True)
    original = parse_fasta(target)
    selected = top_contigs(original, limit)
    replace_fasta(target, selected)
    print("IVANKA_POSTSELECT_LONGEST",len(original),
          "selected",len(selected),
          "lengths",[len(s) for _, s in selected],file=sys.stderr,flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
