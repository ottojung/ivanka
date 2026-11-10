"""Optional MiCall coverage diagnostics, matching analyze_kive_batches.make_stats.

These values are descriptive: neither missing diagnostics nor their PSI scores
can change the established alignment/time qualification. Do not count multiple
mapped placements as independent sequenced fragments.
"""
import csv
import math
from pathlib import Path

# +1: larger values are preferred; -1: smaller values are preferred.
# In particular, depth sums depend on contig/reference span; interpret
# alongside the corresponding position denominator and saturation counts.
DIRECTIONS = {
    "average_read_depth": 1,
    "total_read_depth": 1,
    "average_concordance": 1,
    "exact_uncovered_bases": -1,
    "exact_uncovered_fraction": -1,
    "exact_uncovered_overlapped_bases": -1,
    "soft_clips_count": -1,
    "multimap_max_depth_total": 1,
    "multimap_avg_depth_total": 1,
    "multimap_max_depth_mean": 1,
    "multimap_avg_depth_mean": 1,
    "unique_aligned_fragments": 1,
    "mapped_fragments": 1,
    "multimap_capped_pairs": -1,
    "multimap_oversized_pairs": -1,
    "reference_bases_ge_100": 1,
}
UNITS = {
    "average_read_depth": "coverage per genome_coverage.csv row",
    "total_read_depth": "sum of coverage across genome_coverage.csv rows",
    "average_concordance": "unweighted genome_coverage.csv concordance row mean",
    "exact_uncovered_bases": "zero exact_coverage bases across all contigs",
    "exact_uncovered_fraction": "zero exact_coverage rows / all exact_coverage rows",
    "exact_uncovered_overlapped_bases": "zero inner/overlapped exact_coverage rows",
    "soft_clips_count": "sum max clip per (seed,refseq.nuc.pos)",
    "multimap_max_depth_total": "sum of Q15 maximum depth across contig positions",
    "multimap_avg_depth_total": "sum of Q15 fractional depth across contig positions",
    "multimap_max_depth_mean": "mean Q15 maximum depth across contig positions",
    "multimap_avg_depth_mean": "mean Q15 fractional depth across contig positions",
    "unique_aligned_fragments": "distinct original QNAME pairs with accepted Q15 merged placement",
    "mapped_fragments": "distinct mapped QNAME pairs",
    "multimap_capped_pairs": "pairs at Bowtie2 -k limit; a diagnostic of incompleteness",
    "multimap_oversized_pairs": "pairs omitted by SAM record group size limit",
    "reference_bases_ge_100": "genome_coverage.csv rows with coverage >=100",
}


def _file(folder, name):
    for candidate in (Path(folder) / name, Path(folder) / "scratch" / name):
        if candidate.is_file():
            return candidate
    return None


def _rows(folder, name):
    path = _file(folder, name)
    if path is None:
        return None
    def stream():
        with path.open(newline="", encoding="utf-8") as handle:
            yield from csv.DictReader(handle)
    return stream()


def _number(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def extract(folder):
    """Extract Kive-compatible metrics from one MiCall arm, without failing it.

    Excludes 'unknown' genome-coverage contigs, as make_stats does.
    All absent evidence remains None, never an imputed zero. Reports both
    raw totals and denominators because different assemblies can contain
    different numbers of contigs and coordinate rows.
    """
    values = {name: None for name in DIRECTIONS}
    context = {}
    errors = []
    for filename, func in (
        ("genome_coverage.csv", _genome),
        ("nuc.csv", _soft_clips),
        ("exact_coverage.csv", _exact),
        ("multimap_depth.csv", _multimap),
        ("unique_aligned_fragments.csv", _unique),
        ("remap_counts.csv", _remap),
    ):
        try:
            rows = _rows(folder, filename)
            if rows is None:
                continue
            metrics, metadata = func(rows)
            values.update(metrics)
            context.update(metadata)
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            errors.append(f"{filename}: {type(exc).__name__}: {exc}")
    return {
        "values": values,
        "context": context,
        "unavailable": sorted(k for k, v in values.items() if v is None),
        "errors": errors,
        "qualification_effect": "none",
    }


def _genome(rows):
    depths = []
    concordance = []
    covered = 0
    for row in rows:
        if "unknown" in (row.get("contig") or "").lower():
            continue
        depth = _number(row.get("coverage"))
        if depth is not None:
            depths.append(depth)
            if depth >= 100:
                covered += 1
        value = _number(row.get("concordance"))
        if value is not None:
            concordance.append(value)
    metrics = {
        "average_read_depth": sum(depths) / len(depths) if depths else None,
        "total_read_depth": sum(depths) if depths else None,
        "average_concordance": (sum(concordance) / len(concordance)
                                if concordance else None),
        "reference_bases_ge_100": covered if depths else None,
    }
    return metrics, {"genome_coverage_rows": len(depths),
                     "genome_concordance_rows": len(concordance)}


def _soft_clips(rows):
    # The Kive metric is NOT the sum of clipping.csv rows. Overlapping
    # region rows are deduplicated by the *maximum* at each seed/position.
    clips = {}
    any_rows = False
    for row in rows:
        any_rows = True
        pos = row.get("refseq.nuc.pos")
        if not pos:
            continue
        val = row.get("clip")
        if val in ("", None):
            continue
        number = _number(val)
        if number is None or number < 0 or not number.is_integer():
            continue
        key = (row.get("seed", ""), pos)
        clips[key] = max(clips.get(key, 0), int(number))
    return {"soft_clips_count": sum(clips.values()) if any_rows else None}, {
        "soft_clip_distinct_positions": len(clips)}


def _exact(rows):
    # Kive's analyze_kive_batches reports one longest contig. Direct use of
    # micall.utils.exact_coverage may emit many contigs: explicitly select
    # the longest by number of position rows, not their sum.
    per_contig = {}
    for row in rows:
        contig = row.get("contig", "")
        number = _number(row.get("exact_coverage"))
        if number is None or number < 0 or not number.is_integer():
            continue
        entry = per_contig.setdefault(contig, [0, 0, 0, 0])
        entry[0] += 1
        entry[1] += int(number == 0)
        inner = _number(row.get("exact_coverage_overlapped"))
        if inner is not None and inner >= 0 and inner.is_integer():
            entry[2] += 1
            entry[3] += int(inner == 0)
    if not per_contig:
        return {
            "exact_uncovered_bases": None,
            "exact_uncovered_fraction": None,
            "exact_uncovered_overlapped_bases": None,
        }, {"exact_coverage_rows": 0}
    name, (count, zero, overlap_rows, overlap_zero) = max(
        per_contig.items(), key=lambda x: x[1][0])
    return {
        "exact_uncovered_bases": zero,
        "exact_uncovered_fraction": zero / count,
        "exact_uncovered_overlapped_bases": overlap_zero if overlap_rows else None,
    }, {"exact_coverage_rows": count, "exact_overlapped_rows": overlap_rows,
        "exact_coverage_selected_contig": name,
        "exact_coverage_contigs_considered": len(per_contig)}


def _multimap(rows):
    maximum_total = 0.0
    average_total = 0.0
    n = 0
    for row in rows:
        maximum = _number(row.get("max_depth"))
        average = _number(row.get("avg_depth"))
        if maximum is None or average is None:
            continue
        if maximum < 0 or average < -1e-9 or average > maximum + 1e-9:
            raise ValueError("impossible max/average placement depth")
        maximum_total += maximum
        average_total += average
        n += 1
    return {
        "multimap_max_depth_total": maximum_total if n else None,
        "multimap_avg_depth_total": average_total if n else None,
        "multimap_max_depth_mean": maximum_total/n if n else None,
        "multimap_avg_depth_mean": average_total/n if n else None,
    }, {"multimap_depth_rows": n}


def _unique(rows):
    records = list(rows)
    if len(records) != 1:
        raise ValueError("unique_aligned_fragments.csv must have exactly one row")
    count = _number(records[0].get("unique_aligned_fragments"))
    if count is None or count < 0 or not count.is_integer():
        raise ValueError("invalid unique_aligned_fragments count")
    return {"unique_aligned_fragments": int(count)}, {}


def _remap(rows):
    counts = {}
    for row in rows:
        name = row.get("type")
        if name not in ("remap-fragments", "multimap-capped-pairs",
                        "multimap-oversized-pairs"):
            continue
        value = _number(row.get("count"))
        if value is None or value < 0 or not value.is_integer():
            continue
        if name in counts:
            raise ValueError(f"duplicate remap count: {name}")
        counts[name] = int(value)
    return {
        "mapped_fragments": counts.get("remap-fragments"),
        "multimap_capped_pairs": counts.get("multimap-capped-pairs"),
        "multimap_oversized_pairs": counts.get("multimap-oversized-pairs"),
    }, {}
