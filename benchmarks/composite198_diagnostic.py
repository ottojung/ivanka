"""Offline split 198-sample audit; never a formal qualification."""
import argparse
import csv
import json
from pathlib import Path
from milestone198 import (MANIFEST_SHA256, PANEL_SHA256, SAMPLE_COUNT,
                          SAMPLE_CAP_SECONDS, qualify)
from composite198_source import sha, reinterpret, load_sources


def audit(paths, manifest):
    if sha(manifest) != MANIFEST_SHA256:
        raise ValueError("Frozen manifest SHA256 mismatch")
    with manifest.open() as source:
        names = [r["sample"] for r in csv.DictReader(source, delimiter="\t")]
    if len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT:
        raise ValueError("Frozen cohort not exactly 198 unique samples")
    records, invocations, hashes = load_sources(paths)
    if len(records) != SAMPLE_COUNT or {r["sample"] for r in records} != set(names):
        raise ValueError("Completed records do not match frozen cohort")
    if len(invocations) != len(set(invocations)) or len({r["sample"] for r in records}) != SAMPLE_COUNT:
        raise ValueError("Duplicate invocation or completed sample")
    iva_ids = {r["iva"]["image_id"] for r in records}
    ivanka_ids = {r["ivanka"]["image_id"] for r in records}
    if len(iva_ids) != 1 or len(ivanka_ids) != 1:
        raise ValueError("Mixed MiCall image IDs")
    checked = [reinterpret(r) for r in records]
    report = qualify([r for r, _ in checked], names, next(iter(iva_ids)),
                     next(iter(ivanka_ids)), SAMPLE_CAP_SECONDS, PANEL_SHA256)
    report.update(kind="split_invocation_offline_diagnostic_not_formal",
                  source_results_sha256=hashes, source_invocations=sorted(invocations),
                  legacy_95_flags_reinterpreted=sorted(r["sample"] for r, changed in checked if changed),
                  manifest_sha256=MANIFEST_SHA256, reference_panel_sha256=PANEL_SHA256,
                  formal_qualification_pass=False, milestone198_pass=False)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--results", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() in {x.resolve() for x in args.results}:
        raise ValueError("Output would overwrite a source")
    report = audit(args.results, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output.chmod(0o600)
    print(json.dumps({k: report[k] for k in ("milestone198_valid_pairs",
        "score_psi", "time_psi", "formal_qualification_pass")}, sort_keys=True))


if __name__ == "__main__":
    main()
