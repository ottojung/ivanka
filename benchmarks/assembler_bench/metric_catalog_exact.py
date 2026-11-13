"""Comparable final-MAX exact-read coverage measurements and definitions."""
FIELDS = (
    ("length", "Sequence length", "bases", "higher"),
    ("mean", "Mean depth", "reads / base", "higher"),
    ("median", "Median depth", "reads / base", "higher"),
    ("minimum", "Minimum depth", "reads / base", "higher"),
    ("maximum", "Maximum depth", "reads / base", "unspecified"),
    ("zero_count", "Zero-depth bases", "bases", "lower"),
    ("zero_fraction", "Zero-depth fraction", "fraction", "lower"),
    ("longest_zero_run", "Longest zero-depth stretch", "bases", "lower"),
    ("breadth_ge_1", "Coverage", "fraction", "higher"),
    ("breadth_ge_3", "Coverage at ≥3", "fraction", "higher"),
    ("breadth_ge_10", "Coverage at ≥10", "fraction", "higher"),
    ("breadth_ge_100", "Coverage at ≥100", "fraction", "higher"),
    ("p10", "10th-percentile depth", "reads / base", "higher"),
    ("p25", "25th-percentile depth", "reads / base", "higher"),
    ("p50", "50th-percentile depth", "reads / base", "higher"),
    ("p75", "75th-percentile depth", "reads / base", "higher"),
    ("p90", "90th-percentile depth", "reads / base", "higher"),
)
TRACKS = (
    ("exact_coverage", "Exact read", "Full-span"),
    ("exact_coverage_overlapped", "Exact interior read", "Interior"),
)


def catalog():
    return {track + "_" + key: (
        f"{title} {label.lower()}", unit)
        for track, title, _ in TRACKS for key, label, unit, _ in FIELDS}


def explanations():
    return {track + "_" + key: (
        f"{label} for the {scope.lower()} exact-match depth per base, "
        "computed by MiCall from original R1/R2 reads against the longest "
        "final MAX consensus. Full read matching must have no substitutions "
        "or indels, includes both orientations and all exact placements. "
        + ("Depth is counted across the whole matched read."
           if scope == "Full-span" else
           "Read ends are excluded by 70 bases at each end."),
        "Bases in the selected longest final MAX consensus; read placements "
        "are not unique molecules or approximate mapper alignments.",
        "Final MiCall consensus / exact paired-FASTQ read matching", direction)
        for track, _, scope in TRACKS
        for key, label, _, direction in FIELDS}


def values(report):
    result = {}
    for track, _, _ in TRACKS:
        data = report["tracks"][track]
        for key, _, _, _ in FIELDS:
            metric = data["quantiles"][key] if key.startswith("p") else data[key]
            result[track + "_" + key] = metric
    return result
