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


def _header_identity(header):
    """Match native FASTQ's original-mate identity semantics."""
    words = header[1:].split() if header.startswith("@") else []
    if not words:
        raise ValueError("Invalid paired FASTQ header")
    name, mate = words[0], None
    if name.endswith(("/1", "/2")):
        name, mate = name[:-2], int(words[0][-1])
    if not name:
        raise ValueError("Empty paired FASTQ identifier")
    if len(words) > 1:
        other = words[1]
        if other.startswith(("1:", "2:")):
            designator = int(other[0])
            if mate is not None and mate != designator:
                raise ValueError("Conflicting paired FASTQ mate designators")
            mate = designator
        elif ":" in other and other[0].isdigit():
            raise ValueError("Invalid paired FASTQ mate metadata")
    return name, mate


def _fastq_record(stream):
    header = stream.readline()
    if not header:
        return None
    bases, plus, quality = (stream.readline() for _ in range(3))
    if not bases or not plus.startswith("+") or not quality:
        raise ValueError("Invalid paired FASTQ record")
    sequence = bases.rstrip().upper()
    if len(sequence) != len(quality.rstrip()):
        raise ValueError("Paired FASTQ bases and qualities differ")
    if len(sequence) > 65535:
        raise ValueError("Paired FASTQ read exceeds 65535-base index limit")
    return _header_identity(header), sequence


def paired_reads(paths, limit):
    """Revalidate each scored pair; this is independent of native validation."""
    def op(path):
        return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path, "rt")

    with op(paths[0]) as left, op(paths[1]) as right:
        for _ in range(limit):
            first, second = _fastq_record(left), _fastq_record(right)
            if first is None or second is None:
                if first != second:
                    raise ValueError("Paired FASTQ files have different pair counts")
                return
            (name1, mate1), seq1 = first
            (name2, mate2), seq2 = second
            if (name1 != name2 or (mate1 is None) != (mate2 is None)
                    or mate1 == 2 or mate2 == 1):
                raise ValueError("Paired FASTQ read-pair identifiers disagree")
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
    if not entries:
        # Zero contigs is a valid native result. Preserve the empty FASTA
        # without rereading FASTQs or inventing read-backed candidates.
        return
    if len(entries) <= limit and not trim:
        return
    rank, coverage, pair_counts, depth = read_supported_ranking(
        entries, (paths["--reads1"], paths["--reads2"]), max_pairs,
        with_depth=True,
    )
    chosen = rank[:limit]
    selected = [entries[i] for i in chosen]
    selected_depth = [depth[i] for i in chosen]
    if trim:
        from ivanka_trim_unsupported import (trim_supported_island,
                                             trim_terminal_unsupported)
        island = os.environ.get("IVANKA_TRIM_SUPPORTED_ISLAND", "0") == "1"
        clipping = trim_supported_island if island else trim_terminal_unsupported
        clipped = [clipping(entries[i], depth[i], with_bounds=True)
                   for i in chosen]
        selected = [result for result, _, _ in clipped]
        selected_depth = [depth[i][start:max(start, end - K + 1)]
                          for i, (_, start, end) in zip(chosen, clipped)]
    span = int(os.environ.get("IVANKA_READ_BACKED_MAX_SPAN", "0"))
    if span:
        from ivanka_read_window import dominant_read_window
        selected = [dominant_read_window(result, observed, span)
                    if result == entries[i] else result
                    for i, result, observed in zip(chosen, selected, selected_depth)]
        # A windowed result has no corresponding translated depth slice.
        # The qualified image sets span=0; other values retain their
        # existing (non-tiling) behavior until offset-aware windowing exists.
    tile_span = int(os.environ.get("IVANKA_READ_BACKED_TILE_SPAN", "0"))
    if tile_span:
        tile_overlap = int(os.environ.get("IVANKA_READ_BACKED_TILE_OVERLAP", "0"))
        from ivanka_read_tiling import tile_supported_contig
        selected = [part for i, result, observed in
                    zip(chosen, selected, selected_depth)
                    for part in (tile_supported_contig(result, observed, tile_span,
                                                      overlap=tile_overlap)
                                 if not span or result == entries[i] else [result])]
    write_selected(paths["--output"], selected)
    print("IVANKA_READ_BACKED_SELECTION",
          "native", len(entries), "selected", chosen,
          "covered_31mers", [coverage[i] for i in chosen],
          "supporting_pairs", [pair_counts[i] for i in chosen],
          "read_support_products", [coverage[i] * pair_counts[i] for i in chosen],
          file=sys.stderr, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
