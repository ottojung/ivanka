"""Verify source-attested MiCall fork checkpoints before public reporting."""
import json
import subprocess
from pathlib import Path

from benchmarks.expanded.micall_checkpoint import existing_case, identity
from .hxb2_preview import format_preview, pinned_truth, sha
from .fork_image_attestation import verify

SCHEMA = "ivanka.expanded.fork_micall_synthetic.v1"


def checked(directory, runner, attestation, fork, base):
    folder, runner = Path(directory), Path(runner)
    manifest_file = folder / "run_manifest.json"
    frozen = json.loads(manifest_file.read_text())
    cohort, proof = pinned_truth()
    att = json.loads(Path(attestation).read_text())
    images = frozen["images"]
    if (frozen["schema"] != SCHEMA or frozen["expected"] != 400
            or frozen["limit"] is not None or frozen["qualified"] is not False
            or frozen["truth_proof"] != proof
            or frozen["cohort_sha256"] != sha(cohort_path())
            or frozen["fork_attestation_sha256"] != sha(attestation)
            or att["base_image_sha256"] != base
            or set(images) != set(att["images"])
            or any(att["images"][name]["image_sha256"] != image
                   for name, image in images.items())):
        raise ValueError("fork run manifest / HXB2 truth / image mismatch")
    if verify(images, base, fork) != att:
        raise ValueError("fork binaries differ from independent attestation")
    for name, digest in frozen["benchmark_source_sha256"].items():
        paths = [runner / "benchmarks" / part / name
                 for part in ("expanded", "assembler_bench", "")]
        source = next((path for path in paths if path.is_file()), None)
        if source is None or sha(source) != digest:
            raise ValueError(f"fork benchmark source changed: {name}")
    rows = [json.loads(line) for line in (folder / "results.jsonl").read_text().splitlines()
            if line.strip()]
    if not rows or len(rows) > 400 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("invalid fork checkpoint count / duplicate case")
    cases = {r["id"]: r for r in cohort["cases"]}
    for row in rows:
        case = row["id"]
        if case not in cases:
            raise ValueError("fork checkpoint case not in HXB2 cohort")
        fields = identity(case, {"family": case.rsplit("-s", 1)[0],
                                 "sha256": cases[case]["sha256"]}, proof)
        if existing_case(folder / case, fields, images) != row:
            raise ValueError("fork checkpoint does not match immutable evidence")
    return frozen, rows, sha(folder / "results.jsonl"), att


def cohort_path():
    return Path(__file__).resolve().parents[1] / "expanded/references/hxb2-400-v4-micall-high-depth-cohort.json"


def preview(directory, runner, attestation, fork, base):
    manifest, rows, result_hash, att = checked(
        directory, runner, attestation, fork, base)
    normalized = {
        "images": manifest["images"], "source_truth": manifest["truth_proof"],
        "benchmark_sources_sha256": manifest["benchmark_source_sha256"],
    }
    result = format_preview(
        normalized, rows, result_hash, sha(Path(directory) / "run_manifest.json"))
    result.update(
        id="hxb2-v4-fork-source-attested-live",
        title="HXB2 v4 · source-attested fork MiCall (live)",
        source_commit=subprocess.check_output(
            ["git", "-C", str(runner), "rev-parse", "HEAD"], text=True).strip(),
        source_manifest_sha256=sha(Path(directory) / "run_manifest.json"),
    )
    result["status_reason"] = (
        f"{len(rows)}/400 source-attested fork MiCall cases recorded; "
        "the 598-case expanded gate is NOT qualified.")
    result["micall_fork_provenance"] = {
        "status": "verified",
        "message": "Independently matched all seven fork-commit sources and installed binaries. This is partial data, not a qualification.",
        "attestation_sha256": sha(attestation),
        "base_image_sha256": base,
        "images": {name: {
            "source_commit": v["source_commit"],
            "source_url": v["source_url"],
            "image_sha256": v["image_sha256"],
        } for name, v in att["images"].items()},
    }
    return result
