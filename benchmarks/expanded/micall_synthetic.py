"""Seven integrated-MiCall synthetic arms, with hidden truth entirely off mount.

Source attestations, final MiCall dominant consensus, monotonic container
timings and full failure accounting are mandatory. Partial runs never pass.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time

from benchmarks.podman_detached_lifecycle import run_detached
from benchmarks.assembler_bench.sam_metrics import public_diagnostics
from benchmarks.podman_full_micall import verify_ivanka_image_binding
from .adapters import ASSEMBLERS
from .hxb2_cohort import attestation
from .micall_checkpoint import (
    digest, existing_case, identity, preserve_interrupted, write_case,
)
from .micall_dominant import SCORE_ORIGIN, evaluate_final_dominant
from .micall_retention import prune_case
from .micall_synthetic_constants import TIMING_ORIGIN
from .micall_lock import exclusive_lock
from .run_real import verify_images
from .run_synthetic import cohort_rows

MAX_SECONDS = 1800
TIMER = Path(__file__).resolve().parents[1] / "inside_container_timing.py"


def command(name, image, case_dir, output_dir, identifier, timeout):
    """Every assembler is integrated through the same MiCall analyze CLI."""
    job = "ivanka-bench-synth-" + hashlib.sha256(
        f"{identifier}:{name}:{image}".encode()).hexdigest()[:18]
    base = ["podman", "run", "--rm", "--pull=never", "--network=none",
            "--userns=host", "--cpus=2", "--memory=4g",
            "--name", job, "--timeout", str(timeout),
            "-v", f"{case_dir / 'reads'}:/reads:ro",
            "-v", f"{output_dir}:/results:rw",
            "-v", f"{TIMER}:/ivanka-timer.py:ro",
            "--entrypoint", "/opt/venv/bin/python", image,
            "/ivanka-timer.py", "/results/timing.json",
            "micall", "analyze", "sample",
            "/reads/R1.fastq.gz", "/reads/R2.fastq.gz",
            "/results", "--denovo", "--keep_scratch",
            "--bad_cycles_csv", "/results/bad_cycles.csv",
            "--all_projects"]
    return base


def attempt(case, destination, name, image, timeout):
    case_dir, manifest = case
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "bad_cycles.csv").write_text("tile,cycle\n")
    argv = command(name, image, case_dir, destination,
                   case_dir.name, timeout)
    record = {"status": "failed", "score": 0.0,
              "score_origin": SCORE_ORIGIN,
              "timing_origin": TIMING_ORIGIN, "sha256": image,
              "seconds": None, "argv": argv}
    started = time.monotonic()
    try:
        with (destination / "stdout.log").open("w") as stdout, (
                destination / "stderr.log").open("w") as stderr:
            process = run_detached(argv, stdout, stderr, remaining=timeout)
        record["exit_code"] = process.returncode
        record["podman_stage"] = process.stage
        record["container_wall_seconds"] = round(time.monotonic() - started, 6)
        if process.returncode != 0:
            raise ValueError(f"MiCall exited with code {process.returncode}")
        clock = json.loads((destination / "timing.json").read_text())
        if (clock.get("timing_origin") != TIMING_ORIGIN
                or clock.get("exit_code") != 0
                or not isinstance(clock.get("seconds"), (int, float))
                or clock["seconds"] <= 0
                or clock["seconds"] > record["container_wall_seconds"] + 1):
            raise ValueError("invalid MiCall in-container monotonic timer")
        record["seconds"] = clock["seconds"]
        metrics = evaluate_final_dominant(
            manifest, case_dir / manifest["hidden_truth_file"],
            destination)
        if metrics["score_origin"] != SCORE_ORIGIN:
            raise ValueError("wrong final MiCall score origin")
        record["status"] = "success"
        record["score"] = metrics["score"]
        record["final_dominant"] = metrics["source"]
        record["dominant_exact"] = metrics["dominant_exact"]
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["total_wall_seconds"] = round(time.monotonic() - started, 6)
    # All outcomes retain available downstream diagnostics. Partial/failed
    # artifacts do not turn into successful comparisons.
    record["diagnostics"] = public_diagnostics(destination)
    (destination / "execution.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def run_case(case, root, images, proof, timeout, *, resume=False):
    identifier, directory, manifest = case
    destination = root / identifier
    fields = identity(identifier, manifest, proof)
    if resume:
        reused = existing_case(destination, fields, images)
        if reused is not None:
            return reused
        preserve_interrupted(root, identifier)
    destination.mkdir(exist_ok=False)
    ordering = list(ASSEMBLERS)
    random.Random(int.from_bytes(
        hashlib.sha256(identifier.encode()).digest()[:8], "big")
    ).shuffle(ordering)
    row = {**fields, "execution_order": ordering, "results": {}}
    for name in ordering:
        row["results"][name] = attempt(
            (directory, manifest), destination / name, name,
            images[name], timeout)
    write_case(destination, row)
    # The final scored artifacts are committed before dropping bulky scratch.
    return row


def run(data, output, images, *, jobs=5, timeout=MAX_SECONDS,
        limit=None, resume=False):
    """Hold the same crash-safe lock throughout preflight and execution."""
    with exclusive_lock(output):
        return _run(data, output, images, jobs=jobs, timeout=timeout,
                    limit=limit, resume=resume)


def _run(data, output, images, *, jobs=5, timeout=MAX_SECONDS,
         limit=None, resume=False):
    if jobs not in range(1, 11) or timeout not in range(1, MAX_SECONDS + 1):
        raise ValueError("invalid concurrency or sample lifetime")
    verify_images(images)
    verify_ivanka_image_binding(images["ivanka"])
    proof = attestation(data, expected=400)
    cohort = list(cohort_rows(data))
    if len(cohort) != 400:
        raise ValueError("full 400-case HXB2 cohort required")
    if limit is not None:
        if not 1 <= limit <= 400:
            raise ValueError("invalid development limit")
        cohort = cohort[:limit]
    output = Path(output).resolve()
    expected = run_manifest(proof, images, limit)
    manifest_path = output / "run_manifest.json"
    if resume:
        if not manifest_path.is_file():
            raise ValueError("resume requires a frozen original run manifest")
        if json.loads(manifest_path.read_text()) != expected:
            raise ValueError("resume manifest/image/cohort/code mismatch")
    else:
        output.mkdir(parents=True, exist_ok=False)
        manifest_path.write_text(json.dumps(expected, sort_keys=True,
                                            indent=2)+"\n")
    committed = []
    if resume:
        for case in cohort:
            identifier, _, case_manifest = case
            row = existing_case(output / identifier,
                                identity(identifier, case_manifest, proof),
                                images)
            if row is not None:
                committed.append(row)
        prior = output / "results.jsonl"
        history = output / "resume_history.jsonl"
        with history.open("a") as stream:
            stream.write(json.dumps({
                "prior_results_sha256": digest(prior) if prior.exists() else None,
                "recovered_cases": len(committed),
                "source_manifest_sha256": digest(manifest_path),
            }, sort_keys=True)+"\n")
        recovered = output / "results.recovered.partial"
        with recovered.open("x") as stream:
            for row in sorted(committed, key=lambda row: row["id"]):
                stream.write(json.dumps(row, sort_keys=True)+"\n")
        recovered.replace(prior)
    completed = {row["id"] for row in committed}
    with (output / "results.jsonl").open("a" if resume else "x",
                                         buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            pending = [case for case in cohort if case[0] not in completed]
            futures = [pool.submit(run_case, case, output, images,
                                   proof, timeout, resume=resume)
                       for case in pending]
            for future in as_completed(futures):
                row = future.result()
                stream.write(json.dumps(row, sort_keys=True)+"\n")
                # The checkpoint has been committed and the streamed row
                # flushed. Reuse its independent evidence verifier.
                prune_case(output, row, images, proof)
                print("MICALL_SYNTHETIC_CASE", row["id"], "failures",
                      [name for name, result in row["results"].items()
                       if result["status"] != "success"], flush=True)
    final = output / "results.jsonl"
    completed_rows = [json.loads(line) for line in final.read_text().splitlines()
                      if line.strip()]
    if (len(completed_rows) != len(cohort)
            or len({row["id"] for row in completed_rows}) != len(cohort)):
        raise ValueError("incomplete/duplicate checkpointed synthetic matrix")
    (output / "attempt_completion.json").write_text(json.dumps({
        "schema": "ivanka.micall_synthetic_attempt.v1",
        "status": "ATTEMPTED_NOT_QUALIFIED",
        "cases_attempted": len(cohort), "tools_per_case": len(ASSEMBLERS),
        "result_sha256": digest(final), "source_manifest_sha256": digest(manifest_path),
        "failed_assembler_arms": sum(
            value["status"] != "success" for row in completed_rows
            for value in row["results"].values()),
    }, sort_keys=True, indent=2)+"\n")
    return len(cohort)


def run_manifest(proof, images, limit):
    """Pin all scoring, wrapper and timing sources across restarts."""
    root = Path(__file__).resolve().parent
    sources = ("micall_synthetic.py", "micall_checkpoint.py",
               "micall_retention.py",
               "micall_synthetic_constants.py", "micall_lock.py",
               "micall_dominant.py",
               "score.py", "adapters.py", "hxb2_cohort.py")
    return {
        "schema": "ivanka.expanded.micall_synthetic.v2",
        "status": "INCOMPLETE", "qualified": False,
        "source_truth": proof, "images": images,
        "limit": limit, "expected": 400,
        "threads_per_arm": 2, "memory_limit": "4g",
        "network": "none", "timer": TIMING_ORIGIN,
        "score": SCORE_ORIGIN,
        "instrumentation_sha256": digest(TIMER),
        "diagnostic_sources_sha256": {
            "sam_metrics.py": digest(
                root.parent / "assembler_bench/sam_metrics.py"),
            "diagnostic_metrics.py": digest(
                root.parent / "diagnostic_metrics.py"),
        },
        "benchmark_sources_sha256": {name: digest(root / name)
                                     for name in sources},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int,
                        help="development smoke only, never qualifies")
    parser.add_argument("--resume", action="store_true",
                        help="verify and reuse only complete immutable cases")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    print("INTEGRATED_MICALL_SYNTHETIC_ATTEMPTED",
          run(args.data, args.out, images, jobs=args.jobs,
              timeout=args.timeout, limit=args.limit, resume=args.resume))
    print("NOT A PASS: combine with six complete physical-198 MiCall "
          "comparisons and apply strict expanded all-r gate.")


if __name__ == "__main__":
    main()
