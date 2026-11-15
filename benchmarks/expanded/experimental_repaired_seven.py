"""Audit original HXB2 cases on seven repaired common-MiCall fork images.

This diagnostic never satisfies the canonical dedicated-branch release gate.
It never mounts synthetic truth into the assembler or MiCall containers.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from benchmarks.assembler_bench.dedicated_image_attestation import verify_diagnostic
from .hxb2_cohort import attestation
from .micall_checkpoint import digest, existing_case, identity
from .micall_retention import prune_case
from .micall_synthetic import run_case
from .run_synthetic import cohort_rows

CASES = (
    "coverage_hole-s010", "coverage_hole-s012", "adapter_tails-s013",
    "pcr_jackpot-s011", "minority_30pct-s010", "equal_strains-s014",
    "clonal-s013", "iid_errors-s000",
)
SOURCE_SHA = "74f60e7be6248bdf5019498276036a0ebd339006"
RUST_SHA = "c6869ae6b64385bc4b2922f2f67ed6150e8f9bb3"
SCHEMA = "ivanka.experimental.repaired_common_micall_seven.v1"


def manifest(data, images, report, source):
    root = Path(__file__).resolve().parent
    files = ("experimental_repaired_seven.py", "micall_synthetic.py",
             "micall_checkpoint.py", "micall_retention.py",
             "micall_dominant.py", "score.py", "hxb2_cohort.py")
    return {
        "schema": SCHEMA, "qualified": False,
        "release_qualified": False, "canonical_branch_qualification": False,
        "status": "DIAGNOSTIC_ONLY_NOT_QUALIFIED", "cases": list(CASES),
        "images": images, "common_micall_source_commit": SOURCE_SHA,
        "rust_source_commit": RUST_SHA,
        "original_cohort_sha256": digest(Path(data) / "cohort.json"),
        "attestation_sha256": digest(report),
        "diagnostic_source_commit": source,
        "source_sha256": {name: digest(root / name) for name in files},
    }


def validate_previous(output, candidates, images, proof):
    journal = output / "results.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines()
            if line.strip()] if journal.exists() else []
    assert not journal.exists() or journal.read_bytes().endswith(b"\n")
    seen = set()
    mapping = {case[0]: case for case in candidates}
    for row in rows:
        identifier = row["id"]
        if identifier not in mapping or identifier in seen:
            raise ValueError("invalid or duplicate diagnostic case")
        seen.add(identifier)
        fields = identity(identifier, mapping[identifier][2], proof)
        if existing_case(output / identifier, fields, images) != row:
            raise ValueError("prior row or retained MiCall output was modified")
    return seen


def run(output, data, images_manifest, *, timeout=1800):
    if timeout != 1800:
        raise ValueError("diagnostic timeout must remain 1800 seconds")
    os.environ["CONTAINERS_STORAGE_CONF"] = (
        "/workspace/ivanka-podman-overlay-20261103/storage.conf")
    repo = Path("/workspace/ivanka-repaired-seven-common-pilot-20261115")
    source = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain"], text=True).strip():
        raise ValueError("dirty benchmark source checkout")
    build = json.loads(Path(images_manifest).read_text())
    if (build["qualified"] is not False
            or build["common_micall_commit"] != SOURCE_SHA
            or build["ivanka_native_commit"] != RUST_SHA):
        raise ValueError("unexpected common MiCall/Rust source")
    images, roots = build["images"], build["source_roots"]
    evidence = verify_diagnostic(images, roots,
                                 build["common_micall_image_id"],
                                 "-repaired-20261115")
    proof_path = output / "source-attestation.json"
    if proof_path.exists():
        if json.loads(proof_path.read_text()) != evidence:
            raise ValueError("source attestation changed on resume")
    else:
        output.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(json.dumps(evidence, sort_keys=True, indent=2)+"\n")
    assert evidence["status"].endswith("NOT_QUALIFIED")
    frozen = manifest(data, images, proof_path, source)
    run_manifest = output / "run_manifest.json"
    if run_manifest.exists():
        if json.loads(run_manifest.read_text()) != frozen:
            raise ValueError("source/bench manifest differs on restart")
    else:
        run_manifest.write_text(json.dumps(frozen, sort_keys=True, indent=2)+"\n")
    truth = attestation(data, expected=400)
    cohort = list(cohort_rows(data))
    if len(cohort) != 400:
        raise ValueError("incomplete original synthetic cohort")
    selected = [case for case in cohort if case[0] in CASES]
    if len(selected) != len(CASES) or {case[0] for case in selected} != set(CASES):
        raise ValueError("missing test identities in original HXB2 cohort")
    seen = validate_previous(output, selected, images, truth)
    log = output / "results.jsonl"
    for case in selected:
        name = case[0]
        if name in seen:
            continue
        # A completed but unjournaled case can only be reused after a
        # full independent source/output/hash check by existing_case().
        fields = identity(name, case[2], truth)
        saved = existing_case(output / name, fields, images)
        row = saved if saved is not None else run_case(
            case, output, images, truth, timeout, resume=True)
        with log.open("a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        prune_case(output, row, images, truth)
        print("SEVEN_DIAGNOSTIC_CASE_FINISHED", name,
              {k: r["status"] for k, r in row["results"].items()}, flush=True)
        seen.add(name)
    if seen != set(CASES):
        raise ValueError("incomplete test cohort")
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    status = {"schema": SCHEMA, "status": "ATTEMPTED_NOT_QUALIFIED",
              "release_qualified": False, "cases_attempted": len(rows),
              "failed_arms": sum(x["status"] != "success"
                                 for r in rows for x in r["results"].values()),
              "results_sha256": digest(log),
              "source_attestation_sha256": digest(proof_path),
              "run_manifest_sha256": digest(run_manifest)}
    complete = output / "pilot-finished.json"
    if complete.exists():
        assert json.loads(complete.read_text()) == status
    else:
        complete.write_text(json.dumps(status, sort_keys=True, indent=2)+"\n")
    print("ALL_EIGHT_SEVEN_ARM_CASES_ATTEMPTED_NOT_QUALIFIED", status,flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True)
    args = ap.parse_args()
    run(args.out, args.data, args.images)


if __name__ == "__main__":
    main()
