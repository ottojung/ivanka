"""Complete numeric MiCall CSV and primary SAM diagnostic catalog."""
from benchmarks.diagnostic_metrics import DIRECTIONS, UNITS
from .metric_catalog_micall_rules import RULES

SAM_FIELDS = {
    "records": ("SAM alignment records", "records", "unspecified",
                "All mapped, unmapped, secondary and supplementary SAM records."),
    "duplicates": ("Primary duplicate alignments", "reads", "unspecified",
                   "Primary mapped alignments marked duplicate by SAM flag 0x400."),
    "mapq_unknown": ("Primary reads with unknown MAPQ", "reads", "unspecified",
                     "Primary mapped SAM alignments with mapping quality 255."),
    "read_bases": ("Primary mapped sequenced bases", "nt", "higher",
                   "Query sequence bases in primary mapped SAM alignments."),
    "left_clip_events": ("Left soft-clip events", "events", "lower",
                         "Primary mapped CIGAR soft clips at the left read end."),
    "right_clip_events": ("Right soft-clip events", "events", "lower",
                          "Primary mapped CIGAR soft clips at the right read end."),
    "left_clipped_bases": ("Left soft-clipped bases", "nt", "lower",
                           "Query bases removed by left-end CIGAR S operations."),
    "right_clipped_bases": ("Right soft-clipped bases", "nt", "lower",
                            "Query bases removed by right-end CIGAR S operations."),
    "soft_clip_length_max": ("Longest soft-clip event", "nt", "unspecified",
                             "Maximum CIGAR S operation length on primary mapped reads."),
    "mean_soft_clip_event_length": (
        "Mean soft-clip event length", "nt / event", "lower",
        "Mean number of clipped query bases per primary CIGAR S event."),
}


SAM_DENOMINATORS = {
    "records": "Number of SAM non-header records, including mapped, unmapped, secondary and supplementary alignments.",
    "duplicates": "Primary mapped records with SAM duplicate flag 0x400 / records examined (count, not a rate).",
    "mapq_unknown": "Primary mapped records whose MAPQ field is 255 (unknown); secondary and supplementary are excluded.",
    "read_bases": "Sum of SEQ lengths in primary mapped SAM records; bases include those subsequently soft-clipped.",
    "left_clip_events": "Count of primary mapped alignments whose leftmost non-hard-clipped CIGAR operation is S.",
    "right_clip_events": "Count of primary mapped alignments whose rightmost non-hard-clipped CIGAR operation is S.",
    "left_clipped_bases": "Sum of lengths of the left terminal S operations across primary mapped alignments.",
    "right_clipped_bases": "Sum of lengths of the right terminal S operations across primary mapped alignments.",
    "soft_clip_length_max": "Maximum single CIGAR S operation length across primary mapped alignments; no clips yields zero.",
    "mean_soft_clip_event_length": "Sum of all terminal CIGAR S operation lengths / number of those S operations; no events is unavailable.",
}


def stage(key):
    if key.startswith(("final_contig_", "stitched_", "unstitched_")):
        return "MiCall assembled contig output"
    if key.startswith(("multimap_", "mapped_fragments", "unique_aligned_")):
        return "MiCall multi-placement remapping"
    if key.startswith(("nuc_", "soft_clips_count")):
        return "MiCall nucleotide summary"
    if key.startswith("region_"):
        return "MiCall regional concordance"
    if key.startswith("exact_uncovered_"):
        return "Exact-read coverage CSV when available"
    return "MiCall coverage summary"


def human(key):
    text=key.replace("_"," ").capitalize()
    for old,new in (("Q15","Q15"),("q15","Q15"),("31mer","31-mer"),
                    ("multimap","Multi-map"),("pct","percent")):
        text=text.replace(old,new)
    return text


def catalog():
    return {
        **{key:(human(key),RULES[key][0] if key in RULES else
                ("count" if key.endswith(("count","pairs","fragments",
                                           "bases")) else "measurement"))
            for key in DIRECTIONS
           if key not in ("soft_clips_count",)},
        **{key:(label,unit) for key,(label,unit,_,_) in SAM_FIELDS.items()},
    }


def explanations():
    result={}
    for key in DIRECTIONS:
        if key == "soft_clips_count":
            continue
        raw_unit=UNITS[key]
        direction="higher" if DIRECTIONS[key] == 1 else "lower"
        description,denominator=(RULES[key][1:]
            if key in RULES else (
                f"{human(key)}: {raw_unit}. Computed from recorded MiCall files.",
                f"Original measurement basis: {raw_unit}."))
        result[key]=(description,denominator,stage(key),direction)
    for key,(label,unit,direction,description) in SAM_FIELDS.items():
        result[key]=(
            f"{description} This is a primary-alignment record statistic "
            "from the actual MiCall SAM CIGAR output.",
            SAM_DENOMINATORS[key], "MiCall read-to-contig SAM mapping",
            direction)
    return result
