"""Run all seven image-pinned assemblers without exposing hidden truth.

Each candidate sees only paired reads and its own output directory. Scoring
takes place after container exit, outside the candidate's mount namespace.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time

from .adapters import ASSEMBLERS
from .run_real import verify_images
from .score import dominant_truth_score
from .run_synthetic import cohort_rows
from .synthetic import fingerprint


def commands(name, image, dest, case_dir):
    """The Ivanka process receives exactly the MiCall arguments and no env."""
    base = ["podman", "run", "--rm", "--pull=never", "--userns=host",
            "--network=none", "--cpus=2", "--memory=4g",
            "-v", f"{case_dir / 'reads'}:/reads:ro",
            "-v", f"{dest}:/outputs:rw"]
    if name == "ivanka":
        base += ["--unsetenv-all", "--entrypoint", "/usr/local/bin/ivanka"]
    elif name == "iva":
        base += ["--entrypoint", "/opt/uv-home/.local/bin/iva"]
    else:
        base += ["--entrypoint", "/usr/local/bin/ivanka"]
    base.append(image)
    if name == "iva":
        return base + ["-f", "/reads/R1.fastq.gz", "-r", "/reads/R2.fastq.gz",
                       "-t", "2", "/outputs/iva"], dest / "iva/contigs.fasta"
    return base + ["--reads1", "/reads/R1.fastq.gz",
                   "--reads2", "/reads/R2.fastq.gz",
                   "--output", "/outputs/contigs.fasta"], dest / "contigs.fasta"


def attempt(case_dir, output_dir, name, image, manifest, timeout=1800):
    output_dir.mkdir(parents=True, exist_ok=False)
    argv, fasta = commands(name, image, output_dir, case_dir)
    start = time.monotonic()
    record = {"status": "failed", "sha256": image, "score": 0.0,
              "score_origin": "assembler_fasta_diagnostic_v1",
              "timing_origin": "standalone_container_wall_v1",
              "seconds": None, "argv": argv, "output": str(fasta)}
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
        # Hidden-truth evaluation is a benchmark operation and must never
        # be charged as assembler runtime or depend on the reported tool.
        record["seconds"] = round(time.monotonic() - start, 6)
        record["exit_code"] = result.returncode
        (output_dir / "stderr.log").write_text(result.stderr[-10000:])
        (output_dir / "stdout.log").write_text(result.stdout[-2500:])
        if result.returncode == 0 and fasta.is_file():
            record["output_sha256"] = fingerprint(fasta)
            metrics = dominant_truth_score(
                manifest, case_dir / manifest["hidden_truth_file"], fasta)
            record["score"] = metrics["score"]
            record["truth_diagnostics"] = metrics
            record["status"] = "success"
        else:
            record["error"] = ("assembler nonzero exit" if result.returncode
                               else "successful exit without FASTA")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    if record["seconds"] is None:
        record["seconds"] = round(time.monotonic() - start, 6)
    record["total_wall_seconds"] = round(time.monotonic() - start, 6)
    (output_dir / "execution.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def case_run(case, root, images, timeout):
    case_id, case_dir, manifest = case
    dest = root / case_id
    dest.mkdir(exist_ok=False)
    order = list(ASSEMBLERS)
    random.Random(int.from_bytes(hashlib.sha256(
        case_id.encode()).digest()[:8], "big")).shuffle(order)
    row = {"id": case_id, "cohort": "synthetic",
           "family": manifest["family"],
           "input_sha256": hashlib.sha256(
               (manifest["sha256"]["reads/R1.fastq.gz"] +
                manifest["sha256"]["reads/R2.fastq.gz"]).encode()
           ).hexdigest(),
           "execution_order": order, "results": {}}
    for name in order:
        row["results"][name] = attempt(
            case_dir, dest / name, name, images[name], manifest, timeout=timeout)
    (dest / "matrix.json").write_text(json.dumps(row, sort_keys=True) + "\n")
    return row


def run(cohort, output, images, *, jobs=5, timeout=1800, limit=None):
    if not 1 <= jobs <= 10 or not 1 <= timeout <= 1800:
        raise ValueError("jobs must be 1..10 and timeout 1..1800 seconds")
    verify_images(images)
    all_cases = list(cohort_rows(cohort))
    manifest = json.loads((Path(cohort) / "cohort.json").read_text())
    if len(all_cases) != 400 or manifest.get("samples") != 400:
        raise ValueError("the frozen synthetic cohort must have exactly 400 samples")
    if limit is not None:
        if limit < 1:
            raise ValueError("positive development limit required")
        all_cases = all_cases[:limit]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "provenance.json").write_text(json.dumps({
        "schema": "ivanka.expanded.podman_synthetic.v1",
        "cohort_sha256": fingerprint(Path(cohort) / "cohort.json"),
        "images": images, "threads_per_assembler": 2,
        "memory_limit": "4g", "network": "none",
        "sample_limit": limit, "expected": 400,
    }, sort_keys=True, indent=2) + "\n")
    with (output / "results.jsonl").open("x", buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=jobs) as workers:
            futures = [workers.submit(case_run, case, output, images, timeout)
                       for case in all_cases]
            for future in as_completed(futures):
                row = future.result()
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                done = sum(1 for _ in output.glob("*/matrix.json"))
                print("SYNTHETIC_CASE_DONE", done, "/", len(all_cases),
                      row["id"], "failed",
                      [name for name, r in row["results"].items()
                       if r["status"] != "success"], flush=True)
    return len(all_cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int, default=None,
                        help="development smoke only; never a qualified run")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    print("SYNTHETIC_ATTEMPTED",
          run(args.cohort, args.out, images,
              jobs=args.jobs, timeout=args.timeout, limit=args.limit))
    print("STANDALONE DIAGNOSTICS ONLY: even a complete run cannot qualify "
          "the MiCall pipeline-level benchmark. HXB2 truth and MiCall "
          "final-output scores are mandatory.")


if __name__ == "__main__":
    main()
