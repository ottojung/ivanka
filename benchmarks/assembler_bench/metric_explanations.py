from .metric_catalog_exact import explanations as exact_explanations
from .metric_catalog_micall import explanations as micall_explanations
"""Scientific meaning of public MiCall metrics, including units and denominators.

Preference describes a *conventional* direction, not biological certainty.
Users must choose a direction when constructing diagnostic dominance tests.
"""
# Metric key -> (definition, denominator, MiCall stage, suggested direction).
INFO = {
    "soft_clipped_reads": (
        "Primary mapped alignment records with at least one CIGAR S operation. "
        "Both ends of the same read count once here.",
        "Count; mapped primary alignment records are the reference population.",
        "Read-to-contig SAM alignment", "lower"),
    "soft_clip_events": (
        "CIGAR S operations on primary mapped reads. One read can contribute "
        "a left and right clip event.",
        "Count; per 1,000 mapped primary reads is available separately.",
        "Read-to-contig SAM alignment", "lower"),
    "soft_clipped_bases": (
        "Total nucleotide bases excluded by CIGAR S operations on primary "
        "mapped alignment records.",
        "Count; normalized per 1,000 mapped sequenced bases separately.",
        "Read-to-contig SAM alignment", "lower"),
    "clipped_read_fraction": (
        "Fraction of primary mapped read alignments carrying one or more "
        "soft clips, counting each mapped primary record once.",
        "Soft-clipped primary reads / all mapped primary reads.",
        "Read-to-contig SAM alignment", "lower"),
    "soft_clipped_bases_per_1000_read_bases": (
        "Total soft-clipped nucleotides normalized by mapped primary-read "
        "sequence bases. A shorter clipped fraction is not necessarily "
        "biologically more accurate.",
        "1,000 × clipped bases / mapped primary-read bases.",
        "Read-to-contig SAM alignment", "lower"),
    "soft_clip_events_per_1000_primary_mapped": (
        "Frequency of individual left/right CIGAR S clipping operations "
        "among mapped primary alignment records.",
        "1,000 × clip events / mapped primary reads.",
        "Read-to-contig SAM alignment", "lower"),
    "primary_mapped": (
        "Primary alignment records marked mapped in the SAM. Secondary and "
        "supplementary records are excluded; records need not be unique molecules.",
        "Count of primary mapped alignment records.",
        "Read-to-contig SAM alignment", "higher"),
    "primary_unmapped": (
        "Primary alignment records carrying the SAM unmapped flag. "
        "Not the same as a count of unmatched original read pairs.",
        "Count of primary unmapped alignment records.",
        "Read-to-contig SAM alignment", "lower"),
    "primary_mapped_fraction": (
        "Fraction of primary SAM alignment records marked mapped; this "
        "is a read-record rate, not a genome reconstruction score.",
        "Mapped primary / (mapped + unmapped primary records).",
        "Read-to-contig SAM alignment", "higher"),
    "secondary": (
        "SAM secondary alignments, including alternative placements. "
        "A large count can reflect legitimate multi-mapping rather than errors.",
        "Count of SAM secondary alignment records.",
        "Read-to-contig SAM alignment", "unspecified"),
    "supplementary": (
        "SAM supplementary alignments, often associated with split mappings. "
        "Whether more or fewer is desirable depends on the sample.",
        "Count of SAM supplementary alignment records.",
        "Read-to-contig SAM alignment", "unspecified"),
    "mean_known_mapq": (
        "Mean mapping quality among mapped primary alignment records with "
        "known MAPQ. SAM MAPQ 255 denotes unknown and is excluded.",
        "Sum of known primary MAPQ / primary records with MAPQ != 255.",
        "Read-to-contig SAM alignment", "higher"),
    "mapq_zero": (
        "Mapped primary reads assigned MAPQ 0, which indicates no mapping "
        "confidence on the SAM scale.",
        "Count of mapped primary records with MAPQ 0.",
        "Read-to-contig SAM alignment", "lower"),
    "aligned_read_bases": (
        "Primary mapped nucleotide bases represented by CIGAR M, =, or X. "
        "Excludes soft clips, insertions, and hard clips.",
        "Count of aligned query bases in primary records.",
        "Read-to-contig SAM alignment", "higher"),
    "inserted_bases": (
        "Nucleotide insertions in primary read alignments, from CIGAR I. "
        "True biological indels cannot be classified as errors from this alone.",
        "Count of CIGAR I query bases.",
        "Read-to-contig SAM alignment", "unspecified"),
    "deleted_reference_bases": (
        "Reference-consuming deletions in primary alignments, from CIGAR D. "
        "A deletion is not automatically a sequencing or assembler error.",
        "Count of CIGAR D reference bases.",
        "Read-to-contig SAM alignment", "unspecified"),
    "nuc_soft_clips_count": (
        "MiCall's aggregated per-position nuc.csv clip count. This quantity "
        "has different inclusion and duplication rules than SAM soft clips.",
        "Sum or deduplicated per-position nuc.csv clip aggregate.",
        "MiCall nucleotide summary", "unspecified"),
    "nuc_q15_mean_depth": (
        "Average nucleotide read depth among the positions represented in "
        "MiCall's quality-cutoff-15 nucleotide summary.",
        "Mean depth over represented Q15 nucleotide positions.",
        "MiCall nucleotide summary", "higher"),
    "nuc_q15_covered_fraction": (
        "Fraction of expected positions with supported Q15 nucleotide "
        "coverage, as available in MiCall's nucleotide summary.",
        "Q15-covered positions / positions examined.",
        "MiCall nucleotide summary", "higher"),
    "region_concordance_mean": (
        "Mean MiCall regional concordance between the final result and "
        "the aligned reference panel, evaluated only after assembly.",
        "Mean of valid region concordance percentages.",
        "MiCall regional concordance", "higher"),
    "final_contig_count": (
        "Number of assembled contigs passed to downstream MiCall processing. "
        "Neither more nor fewer alone proves correctness.",
        "Number of final contig records.",
        "MiCall assembler output", "unspecified"),
    "final_contig_total_bases": (
        "Sum of lengths of all final assembled contigs. Overlapping and "
        "duplicate segments are counted repeatedly.",
        "Sum of assembled contig sequence lengths.",
        "MiCall assembler output", "unspecified"),
    "final_contig_31mer_redundancy_fraction": (
        "Proportion of assembled 31-mer instances repeated in other "
        "contigs. A heuristic indicator of redundancy, not misassembly.",
        "Repeated 31-mer instances / eligible 31-mer instances.",
        "MiCall assembler output", "lower"),
}

INFO.update({key: value for key, value in micall_explanations().items()
             if key not in INFO})
INFO.update(exact_explanations())
