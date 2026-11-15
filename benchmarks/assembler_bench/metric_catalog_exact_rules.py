"""Exact-MiCall depth statistics over a single final MAX sequence."""
# Key -> (calculation, normalization / statistical basis).
STATISTICS = {
    "length": (
        "Number of bases in the selected longest final MAX consensus.",
        "One sequence selected by length; no sum across final contigs."),
    "mean": (
        "Sum the exact-match read placement depth at every consensus base, "
        "then divide by sequence length.",
        "All consensus bases, including those with zero exact matches."),
    "median": (
        "Median of exact depth values over all consensus bases; for an even "
        "number of bases, average the two central sorted depths.",
        "All bases in the selected consensus, including zeros."),
    "minimum": (
        "Smallest per-base exact depth over the selected consensus.",
        "All bases, including zeros; not the minimum among covered bases."),
    "maximum": (
        "Largest per-base exact depth over the selected consensus.",
        "All bases; multiple exact read placements contribute separately."),
    "zero_count": (
        "Count of consensus bases with exact-match depth equal to zero.",
        "Every base is evaluated, not only bases where reads map."),
    "zero_fraction": (
        "Number of zero-depth consensus bases divided by sequence length.",
        "Zero-depth bases / all consensus bases, including uncovered ends."),
    "longest_zero_run": (
        "Length of the longest consecutive stretch of zero-depth bases "
        "along the selected consensus.",
        "A run ends when a base has positive depth; measured in bases."),
    "breadth_ge_1": (
        "Count of consensus bases with exact depth at least 1, divided "
        "by total sequence length.",
        "Positive-depth bases / all consensus bases."),
    "breadth_ge_3": (
        "Count of consensus bases with exact depth at least 3, divided "
        "by total sequence length.",
        "Bases with depth ≥3 / all consensus bases."),
    "breadth_ge_10": (
        "Count of consensus bases with exact depth at least 10, divided "
        "by total sequence length.",
        "Bases with depth ≥10 / all consensus bases."),
    "breadth_ge_100": (
        "Count of consensus bases with exact depth at least 100, divided "
        "by total sequence length.",
        "Bases with depth ≥100 / all consensus bases."),
    "p10": (
        "10th percentile of sorted per-base depths using index "
        "round((length − 1) × 0.10).",
        "All bases including zeros; nearest-index quantile, no interpolation."),
    "p25": (
        "25th percentile of sorted per-base depths using index "
        "round((length − 1) × 0.25).",
        "All bases including zeros; nearest-index quantile, no interpolation."),
    "p50": (
        "50th percentile of sorted per-base depths using index "
        "round((length − 1) × 0.50). This may differ from the median.",
        "All bases including zeros; nearest-index quantile, no interpolation."),
    "p75": (
        "75th percentile of sorted per-base depths using index "
        "round((length − 1) × 0.75).",
        "All bases including zeros; nearest-index quantile, no interpolation."),
    "p90": (
        "90th percentile of sorted per-base depths using index "
        "round((length − 1) × 0.90).",
        "All bases including zeros; nearest-index quantile, no interpolation."),
}
