"""Re-score completed Ivanka-only MiCall outputs after authentic IVA cache import.

Never invokes either assembler and never accepts altered artifacts.
"""
import argparse
import csv
import json
from pathlib import Path

from Bio import SeqIO
from milestone198 import MANIFEST_SHA256, PANEL_SHA256, SAMPLE_COUNT, qualify
from podman_full_micall import (DATA, IVA_IMAGE, IVANKA_IMAGE, baseline_provenance,
                               image_id, load_iva_baseline, sha)
from reference_catalog import load_micall_projects
from reference_panel import build_reference_panel, panel_acceptance, panel_sha256


def read_completed(path):
    lines = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    records = [r for r in lines if r.get("status") != "started"]
    if len(records) != SAMPLE_COUNT or len({r.get("sample") for r in records}) != SAMPLE_COUNT:
        raise ValueError("Exactly 198 unique completed records are required")
    if len({r.get("invocation") for r in records}) != 1:
        raise ValueError("One pinned Ivanka invocation required")
    return records


def restore(row, record, results_root, iva_id, ivanka_id, hxb2_hash, panel):
    """Import true IVA final MAX into a completed, checksum-verified Ivanka record."""
    if record["sample"] != row["sample"] or record.get("status") != "finished":
        raise ValueError("Original sample incomplete or identity changed")
    ivanka = record["ivanka"]
    if ivanka.get("exit_code") != 0 or ivanka.get("image_id") != ivanka_id:
        raise ValueError("Original Ivanka arm is incomplete or unpinned")
    folder = Path(ivanka["artifact_dir"]).resolve()
    if not folder.is_relative_to(results_root.resolve()):
        raise ValueError("Original Ivanka artifact path escapes results directory")
    expected = ivanka["metrics"]["outputs"]["conseq.csv"]["sha256"]
    file = next((p for p in (folder / "conseq.csv", folder / "scratch" / "conseq.csv")
                 if p.is_file()), None)
    if not expected or file is None or sha(file) != expected:
        raise ValueError("Original final MAX Ivanka consensus missing or modified")
    provenance = baseline_provenance(row, iva_id, hxb2_hash, all_projects=True)
    if provenance != record.get("provenance"):
        raise ValueError("Original input data or project code changed")
    iva = load_iva_baseline(row["sample"], provenance)
    scored = panel_acceptance(Path(iva["artifact_dir"]), folder, panel, min_ratio=0.90)
    restored = dict(record, iva=iva, iva_baseline_reused=True,
                    best_contig_acceptance=scored, failed=not scored["pass"])
    restored.pop("baseline_error", None)
    restored.pop("evaluation_error", None)
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.results_dir.resolve()):
        raise ValueError("Replay output must not overwrite the original run")
    if sha(DATA / "manifest.tsv") != MANIFEST_SHA256:
        raise ValueError("The original 198-sample manifest changed")
    rows = list(csv.DictReader((DATA / "manifest.tsv").open(), delimiter="\t"))
    names = [r["sample"] for r in rows]
    if len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT:
        raise ValueError("Original full cohort missing or duplicated")
    completed = read_completed(args.results_dir / "results.jsonl")
    by_name = {r["sample"]: r for r in completed}
    if set(by_name) != set(names):
        raise ValueError("Original Ivanka results do not match pinned cohort")
    iva_id, ivanka_id = image_id(IVA_IMAGE), image_id(IVANKA_IMAGE)
    if {r["ivanka"]["image_id"] for r in completed} != {ivanka_id}:
        raise ValueError("Original Ivanka invocation had different image IDs")
    hxb2_hash = sha(DATA / "hxb2.fasta")
    hxb2 = next(SeqIO.parse(DATA / "hxb2.fasta", "fasta")).seq
    projects, _ = load_micall_projects(iva_id)
    panel = build_reference_panel(projects, hxb2)
    if panel_sha256(panel) != PANEL_SHA256 or len(panel) != 33:
        raise ValueError("Frozen reference panel changed")
    scored, errors = [], []
    for row in rows:
        source = by_name[row["sample"]]
        try:
            scored.append(restore(row, source, args.results_dir, iva_id,
                                  ivanka_id, hxb2_hash, panel))
        except (KeyError, OSError, TypeError, ValueError) as exc:
            failed = dict(source, failed=True)
            failed["replay_error"] = f"{type(exc).__name__}: {exc}"
            scored.append(failed)
            errors.append(row["sample"])
    report = qualify(scored, names, iva_id, ivanka_id, 1800, PANEL_SHA256)
    report.update(source_results_sha256=sha(args.results_dir / "results.jsonl"),
                  source_invocation=completed[0]["invocation"],
                  reference_panel_sha256=PANEL_SHA256,
                  manifest_sha256=MANIFEST_SHA256,
                  iva_image_id=iva_id, ivanka_image_id=ivanka_id,
                  unresolved_replay_samples=len(errors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    scored_file = args.output.with_suffix(".scored.jsonl")
    with scored_file.open("w") as out:
        for row in scored:
            out.write(json.dumps(row, sort_keys=True) + "\n")
    args.output.chmod(0o600)
    scored_file.chmod(0o600)
    print("REPLAY_PASS" if report["milestone198_pass"] else "REPLAY_NOT_PASSED",
          "valid", report["milestone198_valid_pairs"],
          "unresolved", len(errors))
    return 0 if report["milestone198_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
