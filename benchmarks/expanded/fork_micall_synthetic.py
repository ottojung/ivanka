"""Replay-verified 400 HXB2 cases through seven exact fork-built MiCall images.

Fork source and installed binaries must match their immutable attestations.
The independently pinned run manifest controls safe checkpoint recovery.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from benchmarks.assembler_bench.image_source_attestation import verify
from .adapters import ASSEMBLERS
from .hxb2_cohort import attestation
from .micall_checkpoint import (
    digest, existing_case, identity, preserve_interrupted,
)
from .micall_retention import prune_case
from .micall_lock import exclusive_lock
from .micall_synthetic import run_case
from .run_synthetic import cohort_rows

SCHEMA = "ivanka.expanded.fork_micall_synthetic.v1"


def checked_images(images, attestation_file, fork, base):
    """Never trust an attestation JSON without rerunning source/binary checks."""
    if set(images) != set(ASSEMBLERS):
        raise ValueError("all seven exact fork image IDs required")
    expected = json.loads(Path(attestation_file).read_text())
    actual = verify(images, attestation_file, fork, base)
    if actual != expected:
        raise ValueError("fork image attestation differs from live installed code")
    return actual


def manifest(data, proof, images, attestation_file, limit):
    here = Path(__file__).resolve()
    sources = (here, here.with_name("micall_synthetic.py"),
               here.with_name("micall_checkpoint.py"),
               here.with_name("micall_retention.py"),
               here.with_name("micall_dominant.py"),
               here.with_name("score.py"),
               here.parents[1] / "inside_container_timing.py",
               here.parents[1] / "assembler_bench/fork_image_attestation.py",
               here.parents[1] / "assembler_bench/dedicated_image_attestation.py",
               here.parents[1] / "assembler_bench/image_source_attestation.py")
    return {
        "schema": SCHEMA,
        "status": "ATTEMPTED_NOT_QUALIFIED",
        "qualified": False, "expected": 400, "limit": limit,
        "cohort_sha256": digest(Path(data) / "cohort.json"),
        "truth_proof": proof,
        "fork_attestation_sha256": digest(attestation_file),
        "images": images,
        "benchmark_source_sha256": {
            source.name: digest(source) for source in sources},
    }


def recover(rows, output, images, proof):
    recovered = []
    for identifier, directory, input_manifest in rows:
        fields = identity(identifier, input_manifest, proof)
        cached = existing_case(output / identifier, fields, images)
        if cached is not None:
            recovered.append(cached)
        else:
            preserve_interrupted(output, identifier)
    return recovered


def run(data, output, images, fork, base, attestation_file, *,
        jobs=5, timeout=1800, limit=None, resume=False):
    if jobs not in range(1, 11) or timeout not in range(1, 1801):
        raise ValueError("jobs must be <=10 and timeout <=1800 seconds")
    if limit is not None and not 1 <= limit <= 400:
        raise ValueError("development limit must be 1..400")
    output = Path(output).resolve()
    with exclusive_lock(output):
        return _run(data, output, images, fork, base, attestation_file,
                    jobs=jobs, timeout=timeout, limit=limit, resume=resume)


def _run(data, output, images, fork, base, attestation_file, *,
         jobs, timeout, limit, resume):
    checked_images(images, attestation_file, fork, base)
    truth = attestation(data, expected=400)
    cohort = list(cohort_rows(data))
    if len(cohort) != 400:
        raise ValueError("incomplete HXB2 truth cohort")
    if limit is not None:
        cohort = cohort[:limit]
    frozen = manifest(data, truth, images, attestation_file, limit)
    source_manifest = output / "run_manifest.json"
    if resume:
        if not source_manifest.exists() or (
                json.loads(source_manifest.read_text()) != frozen):
            raise ValueError("resume manifest does not match pinned source/images")
    else:
        output.mkdir(parents=True, exist_ok=False)
        source_manifest.write_text(json.dumps(frozen, sort_keys=True,
                                               indent=2) + "\n")
    recovered = recover(cohort, output, images, truth) if resume else []
    done = {record["id"] for record in recovered}
    log = output / "results.jsonl"
    if resume:
        history = output / "resume_history.jsonl"
        with history.open("a") as audit:
            audit.write(json.dumps({
                "prior_results_sha256": digest(log) if log.exists() else None,
                "source_manifest_sha256": digest(source_manifest),
                "recovered_cases": len(recovered)}, sort_keys=True) + "\n")
        recovered_file = output / "results.recovered.partial"
        with recovered_file.open("x") as stream:
            for row in sorted(recovered, key=lambda r: r["id"]):
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        recovered_file.replace(log)
    with log.open("a" if resume else "x", buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(run_case, case, output, images, truth,
                                   timeout) for case in cohort
                       if case[0] not in done]
            for future in as_completed(futures):
                row = future.result()
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                # Validate all case evidence before reclaiming bulky MiCall intermediates.
                prune_case(output, row, images, truth)
                print("FORK_MiCall_CASE", row["id"], "failures", [
                    name for name, arm in row["results"].items()
                    if arm["status"] != "success"], flush=True)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    if len(records) != len(cohort) or len({
            r["id"] for r in records}) != len(cohort):
        raise ValueError("lost/duplicated fork MiCall case checkpoint")
    outcome = {
        "schema": SCHEMA,
        "source_manifest_sha256": digest(source_manifest),
        "result_sha256": digest(log),
        "cases_attempted": len(records), "expected_cases": 400,
        "failed_arms": sum(arm["status"] != "success"
                           for row in records for arm in row["results"].values()),
        "status": "ATTEMPTED_NOT_QUALIFIED",
    }
    (output / "attempt_summary.json").write_text(
        json.dumps(outcome, sort_keys=True, indent=2) + "\n")
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--fork", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    result = run(args.data, args.out, images, args.fork, args.base,
                 args.attestation, jobs=args.jobs, timeout=args.timeout,
                 limit=args.limit, resume=args.resume)
    print("FORK_SOURCE_VERIFIED_MICALL_ATTEMPTED",
          result["cases_attempted"], result["status"])
    print("NOT QUALIFIED: compare full 198-real and 400-HXB2 results "
          "with the strict independently verified seven-way PSI gate.")


if __name__ == "__main__":
    main()
