"""Read-only recomputation of the physical-198 paired exact-coverage baseline.

This tool derives the paired Ivanka-versus-IVA diagnostics from preserved,
source-verified artifacts only. It never runs an assembler, never edits MiCall
output, frozen images, cached sidecars or publication data, and never reads a
reference, truth panel or evaluator score. Its two inputs are the pinned public
runs publication (for non-exact mapping diagnostics) and the provenance JSON of
the immutable exact-coverage sidecars (for the two perfect-read-match tracks).

A case with no final-MAX sidecar is null, not zero: it is excluded from paired
statistics and listed explicitly. Interior means the default 70-base excluded
track recorded in the sidecar, not a recomputed approximation.
"""
import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

FULL = "exact_coverage"
INTERIOR = "exact_coverage_overlapped"
TRACKS = (FULL, INTERIOR)
KEYS = ("zero_fraction", "mean", "longest_zero_run", "breadth_ge_1")


@dataclass(frozen=True)
class Paired:
    """Signed paired summary; `mean_diff` is first minus second."""

    count: int
    mean_diff: float
    first_greater: int
    second_greater: int
    ties: int

    def as_dict(self):
        return {
            "paired_cases": self.count,
            "mean_difference": self.mean_diff,
            "first_greater": self.first_greater,
            "second_greater": self.second_greater,
            "ties": self.ties,
        }


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_samples(results_jsonl):
    """Original physical order, which is the alias order R001..R198."""
    samples = []
    with Path(results_jsonl).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                samples.append(json.loads(line)["sample"])
    if len(set(samples)) != len(samples):
        raise ValueError("canonical sample order contains duplicates")
    return samples


def provenance(sidecars, cohort, sample, tool):
    """Return sidecar provenance or None when the final MAX is unavailable."""
    token = hashlib.sha256(sample.encode()).hexdigest()
    base = Path(sidecars) / cohort
    # The frozen v6 cache groups by tool before the sample token; newer
    # caches group by token first. Accept both without rewriting either.
    candidates = (
        base / tool / token / tool / "provenance.json",
        base / token / tool / "provenance.json",
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("overlap_size") != 70:
        raise ValueError(f"unexpected overlap size: {path}")
    return report


def track_value(report, track, key):
    """A missing or unavailable track stays null rather than becoming zero."""
    if report is None:
        return None
    values = report.get("tracks", {}).get(track)
    if not isinstance(values, dict) or values.get("status") == "unavailable":
        return None
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _summarize(pairs):
    if not pairs:
        return Paired(0, 0.0, 0, 0, 0)
    differences = [first - second for first, second in pairs]
    return Paired(
        len(pairs),
        sum(differences) / len(pairs),
        sum(first > second for first, second in pairs),
        sum(first < second for first, second in pairs),
        sum(first == second for first, second in pairs),
    )


def paired_exact(sidecars, samples, track, key, first="ivanka", second="iva"):
    """Return the paired summary and the samples excluded for null evidence."""
    pairs = []
    missing_first = []
    missing_second = []
    for index, sample in enumerate(samples, 1):
        left = track_value(provenance(sidecars, "real", sample, first), track, key)
        right = track_value(provenance(sidecars, "real", sample, second), track, key)
        if left is None:
            missing_first.append(index)
        if right is None:
            missing_second.append(index)
        if left is None or right is None:
            continue
        pairs.append((left, right))
    return _summarize(pairs), missing_first, missing_second


def paired_diagnostics(runs, cohort, key, first="ivanka", second="iva"):
    """Pair one mapping diagnostic, preserving absent/null values."""
    publication = json.loads(Path(runs).read_text(encoding="utf-8"))
    selected = next(item for item in publication["runs"]
                    if item["cohort"] == cohort)
    pairs = []
    for sample in selected["samples"]:
        left = sample.get("diagnostics", {}).get(first, {}).get(key)
        right = sample.get("diagnostics", {}).get(second, {}).get(key)
        if (isinstance(left, (int, float)) and not isinstance(left, bool)
                and isinstance(right, (int, float)) and not isinstance(right, bool)):
            pairs.append((left, right))
    return _summarize(pairs)


def per_sample_exact(sidecars, samples, track, key, first="ivanka", second="iva"):
    """Alias-indexed comparator distribution; nulls are explicit, never zero."""
    rows = []
    for index, sample in enumerate(samples, 1):
        left = track_value(provenance(sidecars, "real", sample, first), track, key)
        right = track_value(provenance(sidecars, "real", sample, second), track, key)
        rows.append({
            "alias": f"R{index:03d}",
            "first": left,
            "second": right,
            "difference": None if left is None or right is None else left - right,
        })
    return rows


def recompute(runs, sidecars, results, witness=None):
    """Return the complete read-only baseline summary."""
    samples = canonical_samples(results)
    exact = {}
    missing = {}
    for track in TRACKS:
        for key in KEYS:
            summary, missing_first, missing_second = paired_exact(
                sidecars, samples, track, key)
            exact[f"{track}.{key}"] = summary.as_dict()
            missing[f"{track}.{key}"] = {
                "ivanka": missing_first, "iva": missing_second,
            }
    diagnostic_keys = (
        "average_concordance", "nuc_soft_clips_count",
        "average_read_depth", "unique_aligned_fragments", "total_read_depth",
    )
    diagnostics = {
        key: paired_diagnostics(runs, "real", key).as_dict()
        for key in diagnostic_keys
    }
    sources = {
        "runs_sha256": sha256_file(runs),
        "canonical_sample_count": len(samples),
        "sidecar_overlap_size": 70,
        "sidecar_method": "micall-longest-final-MAX-exact-v2",
    }
    if witness is not None:
        sources["witness_sha256"] = sha256_file(witness)
        witnessed = json.loads(Path(witness).read_text(encoding="utf-8"))["samples"]
        sources["witness_order_matches"] = list(witnessed) == samples
    return {
        "schema": "ivanka.p2.physical-exact-baseline.v1",
        "sources": sources,
        "exact": exact,
        "excluded_cases": missing,
        "diagnostics": diagnostics,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--sidecars", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--witness", type=Path)
    parser.add_argument("--samples", type=Path,
                        help="optional JSON destination for the per-case distribution")
    parser.add_argument("--track", choices=TRACKS, default=FULL)
    parser.add_argument("--key", choices=KEYS, default="zero_fraction")
    parser.add_argument("--distribution", action="store_true")
    args = parser.parse_args(argv)
    if args.distribution:
        rows = per_sample_exact(
            args.sidecars, canonical_samples(args.results), args.track, args.key)
        output = {"schema": "ivanka.p2.physical-exact-distribution.v1",
                  "rows": rows}
    else:
        output = recompute(args.runs, args.sidecars, args.results, args.witness)
    text = json.dumps(output, indent=1, sort_keys=True)
    if args.samples is not None:
        args.samples.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
