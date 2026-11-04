"""Independently cross-check immutable outputs against a successful 198 runner.

Read-only. A matching digest proves artifact integrity, not biological correctness
or actual execution of a container. Never repairs or reuses a failed invocation.
"""
import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path

from milestone198 import (IVA_IMAGE_SHA256, MANIFEST_SHA256, PANEL_SHA256,
                          SAMPLE_COUNT, qualify)
from summary_198 import evaluate


def sha(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def completed_events(path, invocation, names):
    with path.open() as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    started = [row for row in rows if row.get("status") == "started"]
    finished = [row for row in rows if row.get("status") == "finished"]
    if (len(rows) != 2 * SAMPLE_COUNT or len(started) != SAMPLE_COUNT
            or len(finished) != SAMPLE_COUNT):
        raise ValueError("Not exactly 198 started and 198 finished events")
    for events in (started, finished):
        if ({r.get("sample") for r in events} != set(names)
                or len({r.get("sample") for r in events}) != SAMPLE_COUNT
                or any(r.get("invocation") != invocation for r in events)):
            raise ValueError("Event sample set or invocation is inconsistent")
    return finished


def checked_artifact(folder, expected_sha):
    artifact = next((p for p in (folder / "conseq.csv",
                  folder / "scratch" / "conseq.csv") if p.is_file()), None)
    if (not isinstance(expected_sha, str) or len(expected_sha) != 64
            or artifact is None or not artifact.resolve().is_relative_to(folder.resolve())
            or sha(artifact) != expected_sha):
        raise ValueError("Missing or modified final MAX consensus")
    return artifact


def verify_pair(record, root, cache, invocation, image):
    sample = record["sample"]
    ivanka, iva = record["ivanka"], record["iva"]
    folder = Path(ivanka["artifact_dir"]).resolve()
    expected = (root / invocation / sample / "ivanka").resolve()
    if folder != expected or not folder.is_relative_to(root.resolve()):
        raise ValueError("Candidate artifact escaped the physical invocation")
    if ivanka.get("image_id") != image or iva.get("image_id") != IVA_IMAGE_SHA256:
        raise ValueError("MiCall image IDs changed")
    checked_artifact(folder, ivanka["metrics"]["outputs"]["conseq.csv"]["sha256"])
    cache_dir = (cache / sample).resolve()
    if cache_dir != (cache.resolve() / sample):
        raise ValueError("Cached IVA artifact escaped the cache")
    path = cache_dir / "baseline.json"
    if not path.resolve().is_relative_to(cache_dir):
        raise ValueError("IVA metadata escaped its verified cache directory")
    stored = json.loads(path.read_text())
    if (stored.get("provenance") != record.get("provenance")
            or stored["iva"]["image_id"] != IVA_IMAGE_SHA256
            or stored["iva"]["metrics"]["outputs"]["conseq.csv"]["sha256"]
            != iva["metrics"]["outputs"]["conseq.csv"]["sha256"]):
        raise ValueError("Original cached IVA provenance mismatch")
    checked_artifact(cache_dir, iva["metrics"]["outputs"]["conseq.csv"]["sha256"])



def validate_prior_attestation(path, root, summary_path, summary, invocation, image):
    """Pin immutable historical records before reassessing their current PSI."""
    previous = json.loads(Path(path).read_text())
    expected = {
        "attestation": "read_only_artifact_integrity_and_recorded_psi",
        "pass": True, "invocation": invocation,
        "verified_samples": SAMPLE_COUNT,
        "original_iva_image_id": IVA_IMAGE_SHA256,
        "candidate_image_id": image,
        "manifest_sha256": MANIFEST_SHA256,
        "reference_panel_sha256": PANEL_SHA256,
        "results_sha256": sha(root / "results.jsonl"),
        "summary_sha256": sha(summary_path),
        "score_psi": summary.get("score_psi"),
        "time_psi": summary.get("time_psi"),
    }
    if any(previous.get(key) != value for key, value in expected.items()):
        raise ValueError("Prior attestation does not pin the recorded run")


def verify(root, state, manifest, cache, invocation, prior_attestation=None):
    if sha(manifest) != MANIFEST_SHA256:
        raise ValueError("Frozen manifest checksum mismatch")
    with manifest.open(newline="") as f:
        names = [r["sample"] for r in csv.DictReader(f, delimiter="\t")]
    if len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT:
        raise ValueError("Frozen cohort must have 198 distinct samples")
    if (not (state / "exit_code").is_file()
            or not (state / "finished_at").is_file()
            or (state / "exit_code").read_text().strip() != "0"):
        raise ValueError("Physical runner did not finish successfully")
    summary_path = root / ("summary-" + invocation + ".json")
    summary = json.loads(summary_path.read_text())
    check = evaluate(summary)
    if summary.get("invocation") != invocation or not check["pass"]:
        raise ValueError("Original runner summary is not a strict milestone pass")
    rows = completed_events(root / "results.jsonl", invocation, names)
    image = summary["images"]["ivanka"]
    for record in rows:
        verify_pair(record, root, cache, invocation, image)
    independent = qualify(rows, names, IVA_IMAGE_SHA256, image,
                          summary["sample_limit_seconds"], PANEL_SHA256)
    if (not independent["milestone198_pass"]
            or summary.get("milestone198_valid_pairs")
            != independent["milestone198_valid_pairs"]):
        raise ValueError("Recomputed paired acceptance disagrees with runner")
    recorded_psi_matches = all(summary.get(key) == independent[key]
                               for key in ("score_psi", "time_psi"))
    if prior_attestation is not None:
        validate_prior_attestation(prior_attestation, root, summary_path,
                                   summary, invocation, image)
    if not recorded_psi_matches and prior_attestation is None:
        raise ValueError("Current PSI differs from the original runner; "
                         "supply a verified prior attestation for reassessment")
    return {
        "attestation": ("read_only_artifact_integrity_and_recorded_psi"
                        if recorded_psi_matches else
                        "read_only_artifact_integrity_and_current_psi_reassessment"),
        "recorded_psi_matches_current": recorded_psi_matches,
        "prior_attestation_sha256": (sha(prior_attestation)
                                     if prior_attestation is not None else None),
        "invocation": invocation, "verified_samples": len(rows),
        "original_iva_image_id": IVA_IMAGE_SHA256,
        "candidate_image_id": image,
        "manifest_sha256": MANIFEST_SHA256,
        "reference_panel_sha256": PANEL_SHA256,
        "results_sha256": sha(root / "results.jsonl"),
        "summary_sha256": sha(summary_path),
        "score_psi": independent["score_psi"],
        "time_psi": independent["time_psi"],
        "pass": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--iva-cache", required=True, type=Path)
    parser.add_argument("--invocation", required=True)
    parser.add_argument("--prior-attestation", type=Path,
                        help="Pin an earlier successful artifact attestation "
                             "when recomputing PSI under the current definition")
    args = parser.parse_args()
    try:
        report = verify(args.results_dir, args.state_dir, args.manifest,
                        args.iva_cache, args.invocation, args.prior_attestation)
    except (KeyError, IndexError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"pass": False, "error": str(exc)}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
