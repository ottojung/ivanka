"""Read-only cohort inventory of uniquely flanked, unphased HCV mask targets.

Use only original already-finished MiCall outputs; never infer molecules,
haplotype phase, sample improvement, or permission to replace any mask.
"""
import argparse
import json
import os
from pathlib import Path

from discover_shared_mask_targets import discover, read_sources


def inventory(cohort, anchor=31, minimum_length=20, region_contains="HCV",
              expected_samples=None):
    """Attest per-sample source hashes while collecting candidate metadata."""
    root = Path(cohort).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Expected an existing result-run directory")
    samples = sorted(path for path in root.iterdir() if path.is_dir())
    if (not samples or expected_samples is not None
            and len(samples) != expected_samples):
        raise ValueError("Missing or unexpected number of sample directories")
    result = []
    for sample in samples:
        source = sample / "ivanka"
        if not (source / "conseq.csv").is_file() or not (
                source / "remap_conseq.csv").is_file():
            raise ValueError(f"{sample.name}: missing original MiCall evidence")
        rows, references, source_hashes = read_sources(source)
        report = discover(rows, references, anchor, minimum_length,
                          region_contains)
        result.append({
            "sample": sample.name,
            "source_sha256": source_hashes,
            "target_candidates": report["target_candidates"],
            "rejected_masks": report["rejected_masks"],
            "reason_counts": report["reason_counts"],
        })
    return {
        "schema_version": "ivanka.shared_mask_cohort_discovery.v1",
        "sample_count": len(samples),
        "samples_with_candidates": sum(bool(s["target_candidates"]) for s in result),
        "target_candidate_count": sum(len(s["target_candidates"]) for s in result),
        "rejected_mask_count": sum(len(s["rejected_masks"]) for s in result),
        "minimum_mask_length": minimum_length,
        "flank_anchor": anchor,
        "region_contains": region_contains,
        "samples": result,
        "haplotype_phase": "unidentified",
        "independent_physical_molecules_assigned": False,
        "haplotype_specific_depth_assigned": False,
        "modifies_micall_consensus": False,
        "affects_198_acceptance": False,
        "interpretation": ("Unique multi-reference matches containing the target "
                           "are research candidates only; no observed read-pair "
                           "support, full haplotype phase or improvement is inferred."),
    }


def write_private(report, destination, cohort):
    destination = Path(destination).resolve()
    source = Path(cohort).resolve(strict=True)
    if destination == source or source in destination.parents:
        raise ValueError("Cannot write inside original cohort tree")
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if destination.exists():
        if not destination.is_file() or destination.read_text() != encoded:
            raise ValueError("Refusing to overwrite a different report")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort_run", type=Path)
    parser.add_argument("--expected-samples", type=int)
    parser.add_argument("--anchor", type=int, default=31)
    parser.add_argument("--minimum-length", type=int, default=20)
    parser.add_argument("--region-contains", default="HCV")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.expected_samples is not None and args.expected_samples < 1:
            raise ValueError("Expected a positive sample count")
        result = inventory(args.cohort_run, args.anchor, args.minimum_length,
                           args.region_contains, args.expected_samples)
        if args.output is None:
            print(json.dumps(result, sort_keys=True, indent=2))
        else:
            write_private(result, args.output, args.cohort_run)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
