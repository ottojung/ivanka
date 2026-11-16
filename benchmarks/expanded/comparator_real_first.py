"""Independently finish fixed real-198 MiCall comparators before Ivanka.

Frozen original physical FASTQs, shared patched MiCall code, no Ivanka
execution. Failed arms are never reclassified as passing comparisons.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

from .comparator_first import TOOLS, REPO, git, verify_build
from .micall_checkpoint import digest
from .micall_lock import exclusive_lock
from .micall_synthetic_scheduler import execute
from benchmarks.project_references import final_max_sequences
from benchmarks.reference_catalog import load_micall_projects
from benchmarks.reference_panel import (
    best_panel_alignment, build_reference_panel, panel_sha256,
)

REAL_MANIFEST = "4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192"
PANEL_SHA = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
INVOCATION = "six-comparator-real198-20261116"
SOURCES = (
    "benchmarks/expanded/comparator_real_first.py",
    "benchmarks/expanded/comparator_first.py",
    "benchmarks/podman_full_micall.py",
    "benchmarks/reference_panel.py",
    "benchmarks/project_references.py",
    "benchmarks/reference_catalog.py",
    "benchmarks/inside_container_timing.py",
)


def input_hash(row, data):
    """Hash two actual physical FASTQs, never a mutable sample label alone."""
    name = row["sample"]
    source = data / "samples" / name
    mates = [source / f"{name}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    if any(not file.is_file() or file.is_symlink() for file in mates):
        raise ValueError(f"missing original paired FASTQs: {name}")
    return hashlib.sha256("".join(digest(p) for p in mates).encode()).hexdigest()


def load_rows(data):
    file = data / "manifest.tsv"
    if digest(file) != REAL_MANIFEST:
        raise ValueError("physical cohort source manifest changed")
    with file.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 198 or len({r["sample"] for r in rows}) != 198:
        raise ValueError("wrong original 198-sample cohort")
    return rows


def freeze(data, images_file, jobs):
    build = json.loads(Path(images_file).read_text())
    verify_build(build)
    if (git(REPO, "status", "--porcelain")
            or git(REPO, "remote", "get-url", "origin")
            != "https://github.com/ottojung/ivanka.git"):
        raise ValueError("modified benchmark source")
    if jobs not in range(1, 11):
        raise ValueError("must use at most ten MiCall workers")
    rows = load_rows(data)
    inputs = {r["sample"]: input_hash(r, data) for r in rows}
    from Bio import SeqIO
    with (data / "hxb2.fasta").open() as stream:
        hxb2 = next(SeqIO.parse(stream, "fasta")).seq
    projects, catalog_sha = load_micall_projects(build["images"]["iva"])
    references = build_reference_panel(projects, hxb2)
    if len(references) != 33 or panel_sha256(references) != PANEL_SHA:
        raise ValueError("real-198 independent evaluator panel changed")
    frozen = {
        "schema": "ivanka.comparator_first.stitched_counts_real198.v1",
        "status": "DIAGNOSTIC_NOT_QUALIFIED", "qualified": False,
        "release_qualified": False, "expected_samples": 198,
        "expected_arms": 1188, "tools": list(TOOLS),
        "jobs": jobs, "timeout_per_arm": 1800,
        "real_manifest_sha256": REAL_MANIFEST,
        "hxb2_sha256": digest(data / "hxb2.fasta"),
        "reference_panel_sha256": PANEL_SHA,
        "project_catalog_sha256": catalog_sha,
        "source_commit": git(REPO, "rev-parse", "HEAD"),
        "source_sha256": {p: digest(REPO / p) for p in SOURCES},
        "images": build["images"],
        "image_manifest_sha256": digest(images_file),
        "patched_micall_tree": build["source_tree"],
        "original_inputs": inputs,
    }
    return frozen, rows, references, hxb2


def validate(record, frozen, output):
    name, sample = record.get("assembler"), record.get("sample")
    if (name not in TOOLS or sample not in frozen["original_inputs"]
            or record.get("image_id") != frozen["images"][name]
            or record.get("input_sha256") != frozen["original_inputs"][sample]
            or record.get("status") not in ("success", "failed")):
        raise ValueError("unknown or altered frozen physical comparator arm")
    arm = output / INVOCATION / sample / name
    saved = arm / "comparator_execution.json"
    if not saved.is_file() or json.loads(saved.read_text()) != record:
        raise ValueError("physical comparator execution evidence changed")
    runner = record.get("micall", {})
    if (runner.get("artifact_dir") != str(arm)
            or runner.get("image_id") != frozen["images"][name]):
        raise ValueError("physical MiCall source/output binding changed")
    if record["status"] == "success":
        seconds = runner.get("seconds")
        score = record.get("final_max", {}).get("score")
        final = record.get("final_max", {}).get("source_output")
        if (runner.get("exit_code") != 0 or "metrics" not in runner
                or type(seconds) not in (float, int) or not math.isfinite(seconds)
                or seconds <= 0 or type(score) not in (float, int)
                or not math.isfinite(score) or not final
                or final != "conseq.csv"
                or digest(arm / final) != record.get("final_max", {}).get("sha256")
                or record.get("final_max", {}).get("panel_sha256") != PANEL_SHA):
            raise ValueError("invalid MiCall final MAX / timing evidence")
    return sample, name


def history(output, frozen):
    file = output / "results.jsonl"
    if not file.exists():
        return {}
    raw = file.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("truncated physical comparator journal")
    seen = {}
    for line in raw.splitlines():
        row = json.loads(line)
        key = validate(row, frozen, output)
        if key in seen:
            raise ValueError("duplicate physical comparator execution")
        seen[key] = row
    return seen


def discard_success_scratch(record, frozen, output):
    """Only prune reproducible scratch after authentic, fsynced final output."""
    if record["status"] != "success":
        return
    validate(record, frozen, output)
    folder = output / INVOCATION / record["sample"] / record["assembler"]
    scratch = folder / "scratch"
    if scratch.exists():
        if not scratch.is_dir() or scratch.is_symlink():
            raise ValueError("unsafe scratch cleanup path")
        shutil.rmtree(scratch)


def preserve_orphan(output, sample, name):
    arm = output / INVOCATION / sample / name
    if not arm.exists():
        return
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError("untrusted unjournaled physical output")
    archive = output / "_interrupted"
    archive.mkdir(exist_ok=True)
    for index in range(1, 1000):
        target = archive / f"{sample}-{name}-{index:03d}"
        if not target.exists():
            arm.rename(target)
            return
    raise ValueError("too many interrupted original physical attempts")


def run(data, output, images_file, jobs):
    data, output = Path(data).resolve(), Path(output).resolve()
    with exclusive_lock(output):
        frozen, rows, references, hxb2 = freeze(data, images_file, jobs)
        manifest = output / "run_manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text()) != frozen:
                raise ValueError("resume changed physical cohort/image/source")
        else:
            if output.exists():
                raise ValueError("unattested physical output already exists")
            output.mkdir()
            manifest.write_text(json.dumps(frozen, sort_keys=True, indent=2)+"\n")
        old = history(output, frozen)
        for verified in old.values():
            discard_success_scratch(verified, frozen, output)
        pending = [(row, name) for name in TOOLS for row in rows
                   if (row["sample"], name) not in old]
        print("PHYSICAL_COMPARATORS_ONLY", "verified", len(old),
              "pending", len(pending), flush=True)
        os.environ["IVANKA_DATA"] = str(data)
        os.environ["IVANKA_PODMAN_RESULTS"] = str(output)
        os.environ["IVANKA_PODMAN_LIFECYCLE"] = "detached"
        from benchmarks import podman_full_micall as driver
        if (driver.DATA.resolve() != data
                or driver.RESULTS.resolve() != output):
            raise ValueError("MiCall runner paths initialized before frozen binding")

        def worker(item):
            row, name = item
            sample = row["sample"]
            preserve_orphan(output, sample, name)
            reference = str(hxb2) if row.get("project") == "NFLHIVDNA" else None
            details = driver.run_arm(row, name, frozen["images"][name],
                                     reference, 1800, INVOCATION, True)
            outcome = {
                "sample": sample, "assembler": name,
                "input_sha256": frozen["original_inputs"][sample],
                "image_id": frozen["images"][name], "micall": details,
                "status": "failed",
            }
            if details.get("exit_code") == 0 and "metrics" in details:
                try:
                    arm = Path(details["artifact_dir"])
                    score = best_panel_alignment(
                        final_max_sequences(arm), references)
                    source = arm / "conseq.csv"
                    if not source.is_file():
                        raise ValueError("missing post-MiCall MAX source CSV")
                    outcome["final_max"] = {
                        **score, "sha256": digest(source),
                        "source_output": "conseq.csv", "panel_sha256": PANEL_SHA,
                    }
                    outcome["status"] = "success"
                except (OSError, ValueError, TypeError) as exc:
                    outcome["error"] = f"independent post-assembly evaluator: {exc}"
            else:
                outcome["error"] = details.get("error", "MiCall failed")
            arm = output / INVOCATION / sample / name
            with (arm / "comparator_execution.json").open("x") as evidence:
                json.dump(outcome, evidence, sort_keys=True, indent=2)
                evidence.write("\n")
                evidence.flush()
                os.fsync(evidence.fileno())
            return outcome

        with (output / "results.jsonl").open("a", buffering=1) as stream:
            def commit(outcome):
                validate(outcome, frozen, output)
                stream.write(json.dumps(outcome, sort_keys=True)+"\n")
                stream.flush()
                os.fsync(stream.fileno())
                discard_success_scratch(outcome, frozen, output)
                print("PHYSICAL_COMPARATOR_ARM", outcome["assembler"],
                      outcome["sample"], outcome["status"], flush=True)

            with ThreadPoolExecutor(max_workers=jobs) as pool:
                execute(pool, pending, jobs, worker, commit,
                        lambda: shutil.disk_usage(output).free,
                        reserve_per_arm=512 * 1024**2)
        complete = history(output, frozen)
        if len(complete) != 1188:
            raise ValueError("incomplete physical comparator cohort")
        summary = {
            "schema": frozen["schema"], "qualified": False,
            "status": "ATTEMPTED_1188_NOT_RELEASE_QUALIFIED",
            "cases": 198, "arms": len(complete),
            "failed_arms": sum(x["status"] != "success"
                               for x in complete.values()),
            "results_sha256": digest(output / "results.jsonl"),
            "run_manifest_sha256": digest(manifest),
        }
        marker = output / "attempt-finished.json"
        if marker.exists():
            if json.loads(marker.read_text()) != summary:
                raise ValueError("changed recorded physical completion")
        else:
            marker.write_text(json.dumps(summary, sort_keys=True, indent=2)+"\n")
        print("SIX_NON_IVANKA_PHYSICAL_198_ATTEMPT_COMPLETE", summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()
    run(args.data, args.out, args.images, args.jobs)


if __name__ == "__main__":
    main()
