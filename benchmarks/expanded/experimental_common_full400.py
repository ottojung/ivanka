"""Full 400-case experimental seven-arm MiCall study, never release-qualified.

All cases and failed arms stay visible. The canonical branch gate remains
strictly separate until official builds and independent verification succeed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from benchmarks.assembler_bench.dedicated_image_attestation import verify_diagnostic
from .hxb2_cohort import attestation
from .micall_checkpoint import digest
from .micall_synthetic import run as run_seven

ROOT = Path("/workspace/ivanka-nodistance-seven-full400-20261115")
SOURCE = "3ac24bf460c049553f5b6a564833a668a26a1559"
NATIVE = "c6869ae6b64385bc4b2922f2f67ed6150e8f9bb3"
SCHEMA = "ivanka.experimental.common_unlinked_full400.v1"


def freeze(data, images_manifest):
    build = json.loads(Path(images_manifest).read_text())
    if (build["common_micall_commit"] != SOURCE
            or build["ivanka_native_commit"] != NATIVE
            or build["qualified"] is not False
            or set(build["images"]) != set(build["source_roots"])
            or len(build["images"]) != 7):
        raise ValueError("experimental seven-source pin mismatch")
    image_proof = verify_diagnostic(
        build["images"], build["source_roots"],
        build["common_micall_image_id"], "-unlinked-20261115")
    if (image_proof["status"] !=
            "SEVEN_EXPERIMENTAL_BRANCH_IMAGES_VERIFIED_NOT_QUALIFIED"
            or image_proof["qualified"] is not False):
        raise ValueError("temporary branch qualification must be false")
    truth = attestation(data, expected=400)
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(
            ["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip():
        raise ValueError("dirty diagnostic runner checkout")
    files = (
        ROOT / "benchmarks/expanded/experimental_common_full400.py",
        ROOT / "benchmarks/expanded/micall_synthetic.py",
        ROOT / "benchmarks/expanded/micall_checkpoint.py",
        ROOT / "benchmarks/expanded/micall_retention.py",
        ROOT / "benchmarks/expanded/micall_dominant.py",
        ROOT / "benchmarks/expanded/hxb2_cohort.py",
    )
    return {
        "schema": SCHEMA, "qualified": False, "release_qualified": False,
        "canonical_branch_qualification": False,
        "status": "DIAGNOSTIC_ONLY_NOT_QUALIFIED",
        "source_commit": revision, "common_micall_commit": SOURCE,
        "ivanka_source_commit": NATIVE, "expected_cases": 400,
        "assemblies_per_case": 7, "parallel_case_limit": 10,
        "max_seconds_per_arm": 1800,
        "images": build["images"],
        "common_image_id": build["common_micall_image_id"],
        "image_manifest_sha256": digest(images_manifest),
        "image_attestation": image_proof,
        "input_cohort_sha256": digest(Path(data) / "cohort.json"),
        "truth_validation": truth,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
    }


def run(data, output, images_manifest):
    os.environ["CONTAINERS_STORAGE_CONF"] = (
        "/workspace/ivanka-podman-overlay-20261103/storage.conf")
    output = Path(output)
    if not output.parent.is_dir():
        raise ValueError("experiment parent directory missing")
    frozen = freeze(data, images_manifest)
    meta = output.parent / "experimental-source-manifest.json"
    if meta.exists():
        if json.loads(meta.read_text()) != frozen:
            raise ValueError("frozen diagnostic source and images changed")
    else:
        if output.exists():
            raise ValueError("refuse to bind preexisting output to new source pin")
        meta.write_text(json.dumps(frozen, sort_keys=True, indent=2)+"\n")
    complete = output.parent / "experimental-complete.json"
    if complete.exists():
        raise ValueError("experimental cohort already completed")
    # run_seven performs independent SHA attestation of all 400 inputs,
    # validates replayed arms, preserves partial cases as _interrupted,
    # and drops only checked successful scratch after each case.
    reused = (output / "run_manifest.json").is_file()
    run_seven(data, output, frozen["images"], jobs=10, timeout=1800,
              limit=None, resume=reused)
    final = output / "results.jsonl"
    raw = final.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if (not raw.endswith(b"\n") or len(rows) != 400
            or len({r["id"] for r in rows}) != 400):
        raise ValueError("incomplete source-pinned 400-case experiment")
    statuses = {
        "failed_arms": sum(x["status"] != "success"
                           for r in rows for x in r["results"].values()),
        "complete_arms": sum(x["status"] == "success"
                             for r in rows for x in r["results"].values()),
    }
    result = {
        "schema": SCHEMA, "qualified": False,
        "release_qualified": False,
        "status": "ATTEMPTED_NOT_CANONICAL_QUALIFIED",
        "cases": len(rows), "arms": len(rows) * 7, **statuses,
        "source_manifest_sha256": digest(meta),
        "results_sha256": hashlib.sha256(raw).hexdigest(),
        "attempt_completion_sha256": digest(
            output / "attempt_completion.json"),
    }
    complete.write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")
    print("EXPERIMENTAL_SEVEN_400_ATTEMPTED_NOT_QUALIFIED",result,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    args=parser.parse_args()
    run(args.data,args.out,args.images)


if __name__ == "__main__":
    main()
