"""Source-verified, low-priority exact-read sidecars for completed six-arm cases."""
import argparse
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import subprocess

from benchmarks.assembler_bench.exact_backfill import generate_one
from benchmarks.assembler_bench.exact_cache import sidecar
from benchmarks.expanded.hxb2_cohort import attestation
from benchmarks.expanded.micall_checkpoint import identity, reusable_arm
from benchmarks.expanded.run_synthetic import cohort_rows

MIN_FREE_BYTES = 24 * 1024**3


def digest(path):
    with Path(path).open("rb") as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(root):
    stats = os.statvfs(root)
    return stats.f_bavail * stats.f_frsize >= MIN_FREE_BYTES


def load_stage(source, commit):
    """Use exactly the independently frozen six-comparator scoring source."""
    source = Path(source)
    root = source.parents[2]
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != commit or subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"]).strip():
        raise ValueError("six-comparator stage source drift")
    spec = spec_from_file_location("frozen_six_first", source)
    if spec is None or spec.loader is None:
        raise ValueError("six-comparator stage source unavailable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root, data, cache, micall, max_new, six_source, six_commit):
    root, data, cache = Path(root), Path(data), Path(cache)
    if max_new < 0:
        raise ValueError("negative max_new")
    if cache == root or cache.is_relative_to(root):
        raise ValueError("sidecars may not modify source-attested results")
    frozen = root / "run_manifest.json"
    images = json.loads(frozen.read_text())["images"]
    source_sha = digest(frozen)
    truth = attestation(data, expected=464)
    stage = load_stage(six_source, six_commit)
    source = Path(micall) / "micall/utils/exact_coverage.py"
    if digest(source) != "3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee":
        raise ValueError("MiCall exact coverage implementation drift")
    fork = subprocess.check_output(
        ["git", "-C", str(micall), "rev-parse", "HEAD"], text=True).strip()
    counts = {"new": 0, "reused": 0, "failed_arms": 0, "paused": False}
    for identifier, case_dir, case_manifest in cohort_rows(data):
        folder = root / identifier
        evidence = stage.verify_case(
            folder, identity(identifier, case_manifest, truth), images,
            stage.score_origin_for(case_manifest), source_sha)
        if evidence is None:
            continue
        reads = [case_dir / "reads" / f"R{i}.fastq.gz" for i in (1, 2)]
        for tool in (*stage.SIX, "ivanka"):
            if tool in stage.SIX and evidence["statuses"][tool] != "success":
                counts["failed_arms"] += 1
                continue
            record = reusable_arm(
                folder / tool, tool, images[tool],
                stage.score_origin_for(case_manifest))
            if record is None:
                continue
            if record["status"] == "failed":
                counts["failed_arms"] += 1
                continue
            final = record["final_dominant"]
            report = sidecar(cache, "synthetic", identifier, tool)
            if (report / "provenance.json").is_file():
                generate_one(cache, "synthetic", identifier, tool, None,
                             reads, folder / tool / final["source_output"],
                             final["conseq_csv_sha256"], images[tool], fork)
                counts["reused"] += 1
                continue
            if counts["new"] >= max_new:
                return counts
            if not preflight(cache.parent):
                counts["paused"] = True
                return counts
            if any(digest(read) != case_manifest["sha256"]["reads/" + read.name]
                   for read in reads):
                raise ValueError("original synthetic paired reads changed")
            created = generate_one(
                cache, "synthetic", identifier, tool, None, reads,
                folder / tool / final["source_output"],
                final["conseq_csv_sha256"], images[tool], fork)
            counts["new"] += bool(created)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "data", "cache", "micall"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--max-new", type=int, default=6)
    parser.add_argument("--six-source", required=True, type=Path)
    parser.add_argument("--six-commit", required=True)
    args = parser.parse_args()
    print("EXACT_V6_SOURCE_ATTESTED", run(
        args.root, args.data, args.cache, args.micall, args.max_new,
        args.six_source, args.six_commit),
        flush=True)


if __name__ == "__main__":
    main()
