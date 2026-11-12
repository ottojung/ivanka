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
from benchmarks.podman_full_micall import verify_ivanka_image_binding
from .adapters import ASSEMBLERS
from .hxb2_cohort import attestation
from .micall_dominant import SCORE_ORIGIN, evaluate_final_dominant
from .run_real import verify_images
from .run_synthetic import cohort_rows

MAX_SECONDS = 1800
TIMER = Path(__file__).resolve().parents[1] / "inside_container_timing.py"
TIMING_ORIGIN = "micall_in_container_monotonic_v1"


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
    (destination / "execution.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def run_case(case, root, images, proof, timeout):
    identifier, directory, manifest = case
    destination = root / identifier
    destination.mkdir(exist_ok=False)
    ordering = list(ASSEMBLERS)
    random.Random(int.from_bytes(
        hashlib.sha256(identifier.encode()).digest()[:8], "big")
    ).shuffle(ordering)
    row = {
        "id": identifier, "cohort": "synthetic",
        "family": manifest["family"], "truth_validation": proof,
        "input_sha256": hashlib.sha256(
            (manifest["sha256"]["reads/R1.fastq.gz"] +
             manifest["sha256"]["reads/R2.fastq.gz"]).encode()
        ).hexdigest(),
        "execution_order": ordering,
        "results": {},
    }
    for name in ordering:
        row["results"][name] = attempt(
            (directory, manifest), destination / name, name,
            images[name], timeout)
    (destination / "matrix.json").write_text(
        json.dumps(row, sort_keys=True) + "\n")
    return row


def run(data, output, images, *, jobs=5, timeout=MAX_SECONDS, limit=None):
    if jobs not in range(1, 11) or timeout not in range(1, MAX_SECONDS + 1):
        raise ValueError("invalid concurrency or sample lifetime")
    verify_images(images)
    # Verify the *installed* MiCall subprocess executable, exact argv
    # and empty Rust child env before any synthetic tool may execute.
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
    output.mkdir(parents=True, exist_ok=False)
    (output / "run_manifest.json").write_text(json.dumps({
        "schema": "ivanka.expanded.micall_synthetic.v1",
        "status": "INCOMPLETE", "qualified": False,
        "source_truth": proof, "images": images,
        "limit": limit, "expected": 400,
        "threads_per_arm": 2, "memory_limit": "4g",
        "network": "none", "timer": TIMING_ORIGIN,
        "score": SCORE_ORIGIN,
    }, sort_keys=True, indent=2)+"\n")
    with (output / "results.jsonl").open("x", buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(run_case, case, output, images,
                                   proof, timeout) for case in cohort]
            for future in as_completed(futures):
                row = future.result()
                stream.write(json.dumps(row, sort_keys=True)+"\n")
                print("MICALL_SYNTHETIC_CASE", row["id"], "failures",
                      [name for name, result in row["results"].items()
                       if result["status"] != "success"], flush=True)
    return len(cohort)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int,
                        help="development smoke only, never qualifies")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    print("INTEGRATED_MICALL_SYNTHETIC_ATTEMPTED",
          run(args.data, args.out, images, jobs=args.jobs,
              timeout=args.timeout, limit=args.limit))
    print("NOT A PASS: combine with six complete physical-198 MiCall "
          "comparisons and apply strict expanded all-r gate.")


if __name__ == "__main__":
    main()
