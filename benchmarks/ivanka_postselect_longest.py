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


def native_arguments(arguments):
    native = list(arguments)
    for env, flag, upper in (
        ("IVANKA_NATIVE_MAX_CONTIGS", "--max-contigs", 1000),
        ("IVANKA_NATIVE_MAX_PAIRS", "--max-pairs", 1_000_000_000),
    ):
        value = os.environ.get(env, "")
        if not value:
            continue
        count = int(value)
        if not 1 <= count <= upper:
            raise ValueError("Invalid native limit " + env)
        if any(arg == flag or arg.startswith(flag + "=") for arg in native):
            raise ValueError("Native limit already specified: " + flag)
        native.extend([flag, str(count)])
    return native


def small_input_settings(arguments, default_limit):
    threshold = int(os.environ.get("IVANKA_SMALL_FASTQ_BYTES", "0"))
    if threshold < 0:
        raise ValueError("Negative small-input threshold")
    if threshold == 0:
        return None, default_limit
    candidates = []
    for i, value in enumerate(arguments):
        if value == "--reads1" and i + 1 < len(arguments):
            candidates.append(arguments[i + 1])
        elif value.startswith("--reads1="):
            candidates.append(value.partition("=")[2])
    if len(candidates) != 1 or not candidates[0]:
        raise ValueError("Expected exactly one input read-pair path")
    size = Path(candidates[0]).stat().st_size
    if size > threshold:
        return None, default_limit
    keep = int(os.environ.get("IVANKA_SMALL_CONTIGS", "4"))
    primary = int(os.environ.get("IVANKA_SMALL_PRIMARY_SEEDS", "1000"))
    rescue = int(os.environ.get("IVANKA_SMALL_RESCUE_SEEDS", "400"))
    if not 1 <= keep <= 1000 or not 1 <= primary <= 1000 or not 1 <= rescue <= 400:
        raise ValueError("Invalid small-input search parameters")
    environment = os.environ.copy()
    environment["IVANKA_BENCH_PRIMARY_SEEDS"] = str(primary)
    environment["IVANKA_BENCH_RESCUE_SEEDS"] = str(rescue)
    print("IVANKA_SMALL_INPUT", size, "of", threshold,
          "primary", primary, "rescue", rescue, "contigs", keep,
          file=sys.stderr, flush=True)
    return environment, max(default_limit, keep)


def main(arguments):
    limit = int(os.environ.get("IVANKA_POSTSELECT_CONTIGS", "1"))
    if not 1 <= limit <= 1000:
        raise ValueError("IVANKA_POSTSELECT_CONTIGS must be within 1..1000")
    target = output_path(arguments)
    native_env, limit = small_input_settings(arguments, limit)
    subprocess.run([ORIGINAL, *native_arguments(arguments)], check=True, env=native_env)
    original = parse_fasta(target)
    selection = os.environ.get("IVANKA_SELECTOR_MODE", "longest")
    if selection == "longest":
        selected = top_contigs(original, limit)
        supporting_hits = None
    elif selection == "native_first":
        # Preserve Ivanka's own contribution-weighted ranking: it favors
        # the predominant supported haplotype, even when references diverge.
        selected = original[:limit]
        supporting_hits = None
    elif selection == "reference21":
        from ivanka_reference_selector import (
            load_pinned_panel, index_references, select_reference_supported,
        )
        ref_path = os.environ["IVANKA_PINNED_SELECTOR_PANEL"]
        references = load_pinned_panel(ref_path)
        index = index_references(references, k=21)
        selected, supporting_hits = select_reference_supported(
            original, limit, index, k=21
        )
    elif selection == "reference21_diagonal":
        from ivanka_reference_selector import load_pinned_panel
        from ivanka_diagonal_selector import (
            build_position_index, rank_diagonal, preserve_original_order,
            weak_reference_contig_limit,
        )
        ref_path = os.environ["IVANKA_PINNED_SELECTOR_PANEL"]
        references = load_pinned_panel(ref_path)
        index = build_position_index(references, k=21)
        ranking = rank_diagonal(original, index, k=21)
        density_threshold = float(os.environ.get(
            "IVANKA_WEAK_DIAGONAL_DENSITY", "0"
        ))
        weak_keep = int(os.environ.get("IVANKA_WEAK_CONTIGS", "16"))
        limit, density = weak_reference_contig_limit(
            ranking, limit, density_threshold, weak_keep
        )
        if density < density_threshold:
            print("IVANKA_WEAK_REFERENCE", "density", round(density, 5),
                  "threshold", density_threshold, "contigs", limit,
                  file=sys.stderr, flush=True)
        selected, supporting_hits = preserve_original_order(
            original, ranking, limit
        )
    else:
        raise ValueError("Unknown Ivanka post-selector mode")
    replace_fasta(target, selected)
    print("IVANKA_POSTSELECT",selection,"native",len(original),
          "selected",len(selected),
          "lengths",[len(s) for _, s in selected],
          "reference_21mer_hits",supporting_hits,
          file=sys.stderr,flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
