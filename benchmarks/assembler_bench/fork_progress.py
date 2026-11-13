"""Verify source-attested MiCall fork checkpoints before public reporting."""
import json
import hashlib
import subprocess
from pathlib import Path

from benchmarks.expanded.micall_checkpoint import existing_case, identity
from .hxb2_preview import format_preview, pinned_truth, sha
from .image_source_attestation import verify
from .dedicated_image_attestation import SCHEMA as DEDICATED_SCHEMA
from .public_case_metrics import synthetic as published_metrics
from .exact_cache import append as exact_metrics

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
    if verify(images, attestation, fork, base) != att:
        raise ValueError("fork binaries differ from independent attestation")
    for name, digest in frozen["benchmark_source_sha256"].items():
        paths = [runner / "benchmarks" / part / name
                 for part in ("expanded", "assembler_bench", "")]
        source = next((path for path in paths if path.is_file()), None)
        if source is None or sha(source) != digest:
            raise ValueError(f"fork benchmark source changed: {name}")
    # One captured byte snapshot binds every published row to its digest;
    # a concurrently appended checkpoint must not change that evidence.
    contents = (folder / "results.jsonl").read_bytes()
    if contents and not contents.endswith(b"\n"):
        raise ValueError("incomplete synthetic checkpoint append")
    rows = [json.loads(line) for line in contents.splitlines() if line.strip()]
    if len(rows) > 400 or len({r["id"] for r in rows}) != len(rows):
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
    return frozen, rows, hashlib.sha256(contents).hexdigest(), att


def cohort_path():
    return Path(__file__).resolve().parents[1] / "expanded/references/hxb2-400-v4-micall-high-depth-cohort.json"


def preview(directory, runner, attestation, fork, base, *,
            checked_result=None, exact_root=None):
    # The caller may supply a checkpoint already verified by checked().
    # Re-reading here would mix two generations of an active run.
    manifest, rows, result_hash, att = (
        checked_result if checked_result is not None
        else checked(directory, runner, attestation, fork, base))
    normalized = {
        "images": manifest["images"], "source_truth": manifest["truth_proof"],
        "benchmark_sources_sha256": manifest["benchmark_source_sha256"],
    }
    result = format_preview(
        normalized, rows, result_hash, sha(Path(directory) / "run_manifest.json"))
    for sample, record in zip(result["samples"],
                              sorted(rows, key=lambda row: row["id"])):
        for name in result["tools"]:
            arm = record["results"][name]
            if (arm["status"] == "success"
                    and sample["score"][name] != arm.get("score")):
                raise ValueError("diagnostic source and verified score diverged")
        sample["diagnostics"], sample["exact_profiles"] = {}, {}
        for name in result["tools"]:
            source = record["results"][name]
            score = source.get("final_dominant") or {}
            values, profile = exact_metrics(
                published_metrics(source), exact_root, "synthetic",
                record["id"], name, score.get("conseq_csv_sha256"),
                manifest["images"][name])
            sample["diagnostics"][name] = values
            if profile is not None:
                sample["exact_profiles"][name] = profile
    dedicated = att["schema"] == DEDICATED_SCHEMA
    result.update(
        id=("hxb2-v4-dedicated-source-live" if dedicated
            else "hxb2-v4-fork-source-attested-live"),
        title=("HXB2 v4 · dedicated seven-assembler MiCall (updating)"
               if dedicated else
               "HXB2 v4 · source-attested fork MiCall (diagnostic)"),
        date="2026-11-13",
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
        "attestation_schema": att["schema"],
        "base_image_sha256": base,
        "images": {name: {
            "source_commit": v["source_commit"],
            "source_url": v["source_url"],
            "image_sha256": v["image_sha256"],
            **({"source_branch": v["source_branch"]}
               if "source_branch" in v else {}),
        } for name, v in att["images"].items()},
    }
    return result
