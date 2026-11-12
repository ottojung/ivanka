"""Strict seven-image *MiCall pipeline* comparison on HXB2 synthetic reads.

The browser-facing bench uses MiCall's FINAL Q15 MAX consensus, never the
assembler's standalone FASTA. Each tool receives only paired reads and its
own output directory; truth exists solely in the independent evaluator.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import time

from .adapters import ASSEMBLERS
from .micall_dominant import evaluate_final_dominant, SCORE_ORIGIN
from .fastq_preflight import verify_pairs
from .run_real import verify_images
from .synthetic import FAMILIES, fingerprint

ORIGIN = "micall_in_container_monotonic_v1"
TIMER = Path(__file__).resolve().parents[1] / "inside_container_timing.py"


def command(name, image, case, output, *, timeout=1800):
    """Use the SAME MiCall analysis boundary for all seven candidates."""
    return [
        "podman", "run", "--rm", "--pull=never", "--userns=host",
        "--network=none", "--cpus=2", "--memory=4g",
        "--timeout", str(max(1, timeout - 2)), "--stop-timeout", "2",
        "-v", f"{case / 'reads'}:/bench/reads:ro",
        "-v", f"{output}:/results:rw",
        "-v", f"{TIMER}:/benchmark-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/benchmark-timer.py", "/results/micall_internal_timing.json",
        "micall", "analyze", "sample",
        "/bench/reads/R1.fastq.gz", "/bench/reads/R2.fastq.gz",
        "/results", "--denovo", "--keep_scratch",
        "--bad_cycles_csv", "/results/bad_cycles.csv",
        "--project_code", "NFLHIVDNA", "--all_projects",
    ]


def timed_result(path, process_exit, wall, *, timeout):
    """Never substitute container startup wall time for MiCall monotonic time."""
    if wall > timeout:
        raise ValueError("whole-container timeout exceeded")
    if process_exit != 0:
        raise ValueError(f"MiCall container failed with exit code {process_exit}")
    if not path.is_file():
        raise ValueError("missing in-container MiCall monotonic timing")
    report = json.loads(path.read_text())
    seconds = report.get("seconds")
    if (report.get("timing_origin") != ORIGIN or
            report.get("exit_code") != 0 or type(seconds) not in (int, float)
            or not math.isfinite(seconds) or not 0 < seconds <= timeout):
        raise ValueError("invalid/ineligible MiCall monotonic timing")
    return seconds


def attempt(case, output, name, image, manifest, *, timeout=1800):
    output.mkdir(parents=True, exist_ok=False)
    argv = command(name, image, case, output, timeout=timeout)
    result = {"status": "failed", "sha256": image, "score": 0.0,
              "seconds": None, "tool": name, "argv": argv,
              "score_origin": SCORE_ORIGIN, "timing_origin": ORIGIN}
    start = time.monotonic()
    try:
        process = subprocess.run(argv, capture_output=True, text=True,
                                 timeout=timeout, check=False)
        wall = time.monotonic() - start
        result["exit_code"] = process.returncode
        (output / "podman.stderr.log").write_text(process.stderr[-12000:])
        (output / "podman.stdout.log").write_text(process.stdout[-2500:])
        result["container_wall_seconds"] = round(wall, 6)
        seconds = timed_result(output / "micall_internal_timing.json",
                               process.returncode, wall, timeout=timeout)
        result["seconds"] = round(seconds, 6)
        result["truth_diagnostics"] = evaluate_final_dominant(
            manifest, case / manifest["hidden_truth_file"], output)
        result["score_origin"] = SCORE_ORIGIN
        result["score"] = result["truth_diagnostics"]["score"]
        result["status"] = "success"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["container_wall_seconds"] = round(time.monotonic() - start, 6)
    (output / "execution.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def case_run(entry, root, images, *, timeout):
    """No reference/truth path ever occurs in the container's argv or mounts."""
    name, case, manifest = entry
    dest = root / name
    dest.mkdir(exist_ok=False)
    order = list(ASSEMBLERS)
    random.Random(int.from_bytes(
        hashlib.sha256(name.encode()).digest()[:8], "big")).shuffle(order)
    mate_hashes = [manifest["sha256"][f"reads/R{i}.fastq.gz"] for i in (1, 2)]
    row = {"id": name, "family": manifest["family"], "cohort": "synthetic",
           "source": "micall_final_read_supported_dominant", "execution_order": order,
           "input_sha256": hashlib.sha256("".join(mate_hashes).encode()).hexdigest(),
           "results": {}}
    for tool in order:
        row["results"][tool] = attempt(
            case, dest / tool, tool, images[tool], manifest, timeout=timeout)
    (dest / "matrix.json").write_text(json.dumps(row, sort_keys=True) + "\n")
    return row


def cohort_rows(cohort):
    """Accept a pinned 400-case HXB2 cohort; do not invoke the v1 loader."""
    import re
    root = Path(cohort).resolve()
    cohort_manifest = json.loads((root / "cohort.json").read_text())
    if cohort_manifest.get("schema") != "ivanka.expanded.cohort.v2":
        raise ValueError("only HXB2-anchored v2 synthetic truth is permitted")
    entries = cohort_manifest.get("cases")
    if (not isinstance(entries, list) or len(entries) != 400 or
            cohort_manifest.get("samples") != 400 or
            cohort_manifest.get("seeds_per_family") != 16 or
            set(cohort_manifest.get("families", ())) != set(FAMILIES)):
        raise ValueError("incomplete required 400 HXB2-derived synthetic cases")
    rows = []
    names = set()
    for entry in entries:
        name = entry.get("id")
        if (not isinstance(name, str) or
                not re.fullmatch(r"[a-z][a-z0-9_]*-s[0-9]{3}", name) or
                name in names):
            raise ValueError("unsafe, missing or duplicate synthetic case name")
        names.add(name)
        directory = (root / name).resolve()
        if directory.parent != root or not directory.is_dir():
            raise ValueError(name + ": missing or unsafe case directory")
        record = json.loads((directory / "manifest.json").read_text())
        if (record.get("schema") != "ivanka.expanded.synthetic.v2" or
                record.get("family") not in FAMILIES or
                record.get("read_files") !=
                ["reads/R1.fastq.gz", "reads/R2.fastq.gz"] or
                record.get("hidden_truth_file") != "hidden-truth/haplotypes.fasta" or
                not isinstance(record.get("ancestry"), dict) or
                record.get("sha256") != entry.get("sha256")):
            raise ValueError(name + ": invalid HXB2 ancestry/FASTQ manifest")
        for name_of_file, expected_hash in record["sha256"].items():
            f = (directory / name_of_file).resolve()
            if (not f.is_relative_to(directory) or not f.is_file()
                    or not isinstance(expected_hash, str) or
                    fingerprint(f) != expected_hash):
                raise ValueError(name + ": synthetic input/truth hash drift")
        verify_pairs(directory / record["read_files"][0],
                     directory / record["read_files"][1], record["pairs"])
        rows.append((name, directory, record))
    if {f"{family}-s{seed:03d}"
            for family in FAMILIES for seed in range(16)} != names:
        raise ValueError("wrong fixed synthetic family/seed roster")
    return rows

def run(cohort, output, images, *, jobs=5, timeout=1800, limit=None):
    if not (1 <= jobs <= 10 and 1 <= timeout <= 1800):
        raise ValueError("jobs must be 1..10 and timeout 1..1800")
    verify_images(images)
    rows = cohort_rows(cohort)
    if limit is not None:
        if not 1 <= limit <= len(rows):
            raise ValueError("invalid development-only sample limit")
        rows = rows[:limit]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "provenance.json").write_text(json.dumps({
        "schema": "ivanka.assembler-bench.micall-synthetic.v1",
        "images": images, "cohort_sha256": fingerprint(Path(cohort) / "cohort.json"),
        "score": SCORE_ORIGIN,
        "timing_origin": ORIGIN, "expected": 400,
        "limit": limit, "qualified_run": limit is None,
        "threads_per_assembler": 2, "max_concurrent_cases": jobs,
    }, sort_keys=True, indent=2) + "\n")
    with (output / "results.jsonl").open("x", buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(case_run, case, output, images, timeout=timeout)
                       for case in rows]
            for task in as_completed(futures):
                item = task.result()
                stream.write(json.dumps(item, sort_keys=True) + "\n")
                print("MICALL_SYNTHETIC_CASE", item["id"], "failures",
                      [name for name, value in item["results"].items()
                       if value["status"] != "success"], flush=True)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int, default=None,
                        help="development-only partial run; can NEVER qualify")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    print("MICALL_SYNTHETIC_COMPLETED", run(
        args.cohort, args.out, images, jobs=args.jobs,
        timeout=args.timeout, limit=args.limit))
    print("A passing verdict requires a complete independently validated "
          "400-case HXB2-derived cohort, real-198 arms and the strict gate.")


if __name__ == "__main__":
    main()
