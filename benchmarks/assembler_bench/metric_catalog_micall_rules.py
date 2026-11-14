"""Metric calculation contracts derived from benchmarks.diagnostic_metrics.extract.

Each rule supplies (unit, calculation, denominator/selection). Missing input
files or empty eligible populations produce unavailable values, never zero.
"""
RULES = {
    "average_read_depth": (
        "reads / row",
        "Arithmetic mean of numeric coverage values in genome_coverage.csv. "
        "Rows whose contig name contains 'unknown' are excluded.",
        "Sum of coverage / number of eligible rows with numeric coverage."),
    "total_read_depth": (
        "read-depth sum",
        "Sum of numeric coverage values across genome_coverage.csv rows, "
        "excluding rows with an 'unknown' contig.",
        "All eligible numeric genome_coverage.csv coverage rows; "
        "not normalized by contig span."),
    "average_concordance": (
        "concordance value",
        "Unweighted arithmetic mean of the concordance column in "
        "genome_coverage.csv, ignoring nonnumeric and 'unknown' contig rows.",
        "Sum of valid concordance values / count of valid concordance rows."),
    "exact_uncovered_bases": (
        "bases",
        "Count of exact_coverage.csv positions with exact_coverage = 0 "
        "on the contig having the most valid full-read coverage rows.",
        "Eligible positions on the single longest represented contig, "
        "not summed across contigs."),
    "exact_uncovered_fraction": (
        "fraction",
        "Fraction of valid exact_coverage.csv positions with full-read "
        "exact_coverage = 0, on the longest represented contig.",
        "Zero-depth full-read positions / valid positions on that contig."),
    "exact_uncovered_overlapped_bases": (
        "bases",
        "Count of positions with exact_coverage_overlapped = 0 for the "
        "same longest contig selected by full-read positions.",
        "Eligible positions with numeric interior depth on that contig; "
        "interior matching excludes 70 read-end bases."),
    "multimap_max_depth_total": (
        "reads / site, summed",
        "Sum of max_depth from multimap_depth.csv for contig positions "
        "where both max_depth and avg_depth are valid.",
        "All valid multimap_depth.csv position rows; no length normalization."),
    "multimap_avg_depth_total": (
        "reads / site, summed",
        "Sum of fractional avg_depth in multimap_depth.csv at positions "
        "where both max_depth and avg_depth are valid.",
        "All valid multimap_depth.csv rows; ambiguous placements contribute "
        "fractional rather than independent read counts."),
    "multimap_max_depth_mean": (
        "reads / site",
        "Arithmetic mean of max_depth from valid multimap_depth.csv "
        "position rows.",
        "Sum of valid max_depth / number of positions with valid max and avg depth."),
    "multimap_avg_depth_mean": (
        "reads / site",
        "Arithmetic mean of fractional avg_depth from valid "
        "multimap_depth.csv position rows.",
        "Sum of valid avg_depth / number of positions with valid max and avg depth."),
    "unique_aligned_fragments": (
        "fragments",
        "The unique_aligned_fragments field from the single summary row "
        "in unique_aligned_fragments.csv: original pairs with accepted Q15 placement.",
        "One validated summary row; counts distinct original fragments, "
        "not placements."),
    "mapped_fragments": (
        "fragments",
        "Count from the remap-fragments row of remap_counts.csv. "
        "This counts mapped original QNAME pairs, not mapped SAM records.",
        "The single remap-fragments entry; missing summary is unavailable."),
    "multimap_capped_pairs": (
        "pairs",
        "Mapped pairs reaching the Bowtie2 -k reporting limit, taken from "
        "remap_counts.csv when present. Otherwise the maximum count among "
        "per-pass warnings is used as a lower bound, not their sum.",
        "One remap-count entry or a warning-derived lower bound; "
        "two remapping passes may overlap."),
    "multimap_oversized_pairs": (
        "pairs",
        "Number of pairs rejected by the SAM record-group size limit, "
        "from the multimap-oversized-pairs row of remap_counts.csv.",
        "One validated remap count entry; no entry means unavailable."),
    "reference_bases_ge_100": (
        "positions",
        "Count of genome_coverage.csv positions with numeric coverage "
        "at least 100 after excluding 'unknown' contigs.",
        "Eligible position rows, not the length of a common reference genome."),
    "nuc_q15_mean_depth": (
        "reads / site",
        "For q-cutoff 15 nuc.csv rows, keep the greatest numeric coverage "
        "per (seed, refseq.nuc.pos), then average those retained depths.",
        "Sum of deduplicated Q15 coverage / number of distinct valid "
        "(seed, position) entries, including zero-depth entries."),
    "nuc_q15_total_depth": (
        "read-depth sum",
        "Sum of greatest Q15 nuc.csv coverage per (seed, refseq.nuc.pos); "
        "overlapping region rows at the same seed/position count once.",
        "All distinct valid Q15 seed/position entries; not normalized."),
    "nuc_q15_positions_covered": (
        "positions",
        "Count of distinct (seed, refseq.nuc.pos) entries with Q15 "
        "coverage greater than zero, after retaining maximum depth for duplicates.",
        "All distinct valid Q15 seed/position entries."),
    "nuc_q15_covered_fraction": (
        "fraction",
        "Proportion of deduplicated Q15 nuc.csv seed/position entries "
        "whose maximum observed coverage is positive.",
        "Positive-depth Q15 seed/positions / all valid Q15 seed/positions."),
    "region_concordance_mean": (
        "percent",
        "Unweighted mean of numeric pct_concordance in concordance.csv; "
        "rows without valid concordance are ignored.",
        "Sum of valid pct_concordance / count of valid concordance rows; "
        "zero-coverage rows are included when they have numeric concordance."),
    "region_concordance_covered_mean": (
        "percent",
        "Unweighted mean of numeric concordance.csv pct_concordance "
        "only where pct_covered is also numeric and greater than zero.",
        "Valid concordance rows with positive pct_covered; "
        "no weighting by region length or coverage."),
    "final_contig_count": (
        "contigs",
        "Count of nonempty sequence rows in contigs.csv, including "
        "duplicate and unknown-reference contigs.",
        "Nonempty 'contig' or 'sequence' entries; missing/empty files "
        "do not contribute a fabricated zero."),
    "final_contig_total_bases": (
        "nt",
        "Sum of lengths of all nonempty contig sequences in contigs.csv. "
        "Overlapping and repeated sequences each contribute their length.",
        "Nonempty contig rows; not unique genome coverage."),
    "final_contig_unknown_count": (
        "contigs",
        "Count of nonempty contigs.csv sequences whose ref field "
        "contains 'unknown' (case insensitive).",
        "All nonempty contig rows; status is based on ref, not sequence."),
    "final_contig_exact_duplicates": (
        "contigs",
        "Number of contigs.csv sequences identical to a previously observed "
        "sequence after uppercase normalization; the first copy is not counted.",
        "Nonempty sequences; exact matches only, without reverse-complement "
        "normalization."),
    "final_contig_31mer_redundancy_fraction": (
        "fraction",
        "One minus the number of distinct canonical A/C/G/T 31-mers divided "
        "by all valid 31-mer instances across final contig sequences. "
        "A reverse complement shares a canonical 31-mer.",
        "Valid 31-mer windows across nonempty contigs; repeated windows "
        "count repeatedly in the denominator."),
    "stitched_contig_count": (
        "contigs",
        "Number of rows with a nonempty contig field in stitched_contigs.csv.",
        "Nonempty contig rows in this specific intermediate MiCall file."),
    "unstitched_contig_count": (
        "contigs",
        "Number of rows with a nonempty contig field in unstitched_contigs.csv.",
        "Nonempty contig rows in this specific intermediate MiCall file."),
}
