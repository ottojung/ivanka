#!/usr/bin/env python3
"""Emit the best original-read-supported contigs after ordinary native assembly."""
import gzip
import os
from pathlib import Path
import subprocess
import sys
import tempfile

K = 31
COMPLEMENT = str.maketrans("ACGT", "TGCA")
NATIVE = "/usr/local/bin/ivanka-native"


def parse_fasta(path):
    entries = []
    header = None
    sequence = []
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            if header is not None:
                entries.append((header, "".join(sequence)))
            header = line
            sequence = []
        else:
            sequence.append(line.strip().upper())
    if header is not None:
        entries.append((header, "".join(sequence)))
    if not entries:
        raise ValueError("Native assembler emitted no FASTA entries")
    return entries


def paths_from_args(args):
    required = {}
    for key in ("--reads1", "--reads2", "--output"):
        if args.count(key) != 1:
            raise ValueError("Missing or duplicated native argument: " + key)
        position = args.index(key)
        if position + 1 >= len(args):
            raise ValueError("Missing value for " + key)
        required[key] = Path(args[position + 1])
    return required


def index_kmers(entries):
    positions = {}
    for number, (_, sequence) in enumerate(entries):
        for position in range(len(sequence) - K + 1):
            kmer = sequence[position:position + K]
            if all(nucleotide in "ACGT" for nucleotide in kmer):
                positions.setdefault(kmer, []).append((number, position))
                reverse = kmer.translate(COMPLEMENT)[::-1]
                positions.setdefault(reverse, []).append((number, position))
    return {k: v for k, v in positions.items() if len(v) <= 8}


def paired_reads(paths, limit):
    def op(path):
        return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path, "rt")
    with op(paths[0]) as left, op(paths[1]) as right:
        for _ in range(limit):
            h1, h2 = left.readline(), right.readline()
            if not h1 or not h2:
                if h1 != h2:
                    raise ValueError("Paired reads have different lengths")
                return
            seq1, seq2 = left.readline().strip().upper(), right.readline().strip().upper()
            for stream in (left, right):
                stream.readline()
                stream.readline()
            yield seq1, seq2


def rank_by_pair_weighted_breadth(entries, coverage, pairs):
    """Weight supported span and fragment abundance by its observed fraction.

    A long erroneous extension is not a valid dominant assembly just because
    a smaller supported part of it is abundant. All measurements are from
    the original paired FASTQ, without any external sequence.
    """
    return sorted(range(len(entries)),
                  key=lambda i: (
                      -(coverage[i] * coverage[i] * pairs[i]) /
                      max(1, len(entries[i][1]) - K + 1),
                      -coverage[i] * pairs[i], -coverage[i],
                      -pairs[i], -len(entries[i][1]), i))


def read_supported_ranking(entries, reads, max_pairs=80000, *, with_depth=False):
    positions = index_kmers(entries)
    depth = [[0] * max(0, len(sequence) - K + 1) for _, sequence in entries]
    pairs = [0] * len(entries)
    count = 0
    for read1, read2 in paired_reads(reads, max_pairs):
        count += 1
        matches = {}
        for read in (read1, read2):
            for pos in range(0, len(read) - K + 1, 2):
                for candidate, locus in positions.get(read[pos:pos + K], ()):
                    matches.setdefault(candidate, set()).add(locus)
        for candidate, loci in matches.items():
            if len(loci) < 2:
                continue
            pairs[candidate] += 1
            candidate_depth = depth[candidate]
            for locus in loci:
                candidate_depth[locus] += 1
    if count == 0:
        raise ValueError("No original paired reads")
    coverage = [sum(value >= 3 for value in depths) for depths in depth]
    rank = rank_by_pair_weighted_breadth(entries, coverage, pairs)
    if with_depth:
        return rank, coverage, pairs, depth
    return rank, coverage, pairs


def write_selected(path, selected):
    target = Path(path)
    with tempfile.NamedTemporaryFile("w", dir=target.parent,
                                     prefix=".ivanka-selected-", delete=False) as stream:
        scratch = Path(stream.name)
        try:
            for header, sequence in selected:
                stream.write(header + "\n")
                stream.write(sequence + "\n")
        except BaseException:
            scratch.unlink(missing_ok=True)
            raise
    scratch.replace(target)


def main(args):
    paths = paths_from_args(args)
    subprocess.run([NATIVE, *args], check=True)
    entries = parse_fasta(paths["--output"])
    limit = int(os.environ.get("IVANKA_POSTSELECT_CONTIGS", "1"))
    max_pairs = int(os.environ.get("IVANKA_SUPPORT_PAIRS", "80000"))
    if limit < 1 or limit > 1000 or max_pairs < 1 or max_pairs > 1000000:
        raise ValueError("Invalid read-only selection budget")
    trim = os.environ.get("IVANKA_TRIM_UNSUPPORTED_TERMINI", "0") == "1"
    if len(entries) <= limit and not trim:
        return
    rank, coverage, pair_counts, depth = read_supported_ranking(
        entries, (paths["--reads1"], paths["--reads2"]), max_pairs,
        with_depth=True,
    )
    chosen = rank[:limit]
    selected = [entries[i] for i in chosen]
    if trim:
        from ivanka_trim_unsupported import (trim_supported_island,
                                             trim_terminal_unsupported)
        island = os.environ.get("IVANKA_TRIM_SUPPORTED_ISLAND", "0") == "1"
        clipping = trim_supported_island if island else trim_terminal_unsupported
        selected = [clipping(entries[i], depth[i]) for i in chosen]
    span = int(os.environ.get("IVANKA_READ_BACKED_MAX_SPAN", "0"))
    if span:
        from ivanka_read_window import dominant_read_window
        selected = [dominant_read_window(entries[i], depth[i], span)
                    if entries[i] == result else result
                    for i, result in zip(chosen, selected)]
    tile_span = int(os.environ.get("IVANKA_READ_BACKED_TILE_SPAN", "0"))
    if tile_span:
        tile_overlap = int(os.environ.get("IVANKA_READ_BACKED_TILE_OVERLAP", "0"))
        from ivanka_read_tiling import tile_supported_contig
        selected = [part for i, result in zip(chosen, selected)
                    for part in (tile_supported_contig(entries[i], depth[i],
                                                     tile_span, overlap=tile_overlap)
                                 if entries[i] == result else [result])]
    write_selected(paths["--output"], selected)
    print("IVANKA_READ_BACKED_SELECTION",
          "native", len(entries), "selected", chosen,
          "covered_31mers", [coverage[i] for i in chosen],
          "supporting_pairs", [pair_counts[i] for i in chosen],
          "read_support_products", [coverage[i] * pair_counts[i] for i in chosen],
          file=sys.stderr, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
