"""Exact-read diagnostics from original source-attested physical checkpoints."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .current_inputs import physical_pairs, real_arm
from .exact_cache import sidecar
from .resource_retry import select as select_retry

IMAGE_MANIFEST = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
EXACT_MODULE = "3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee"
MIN_FREE_BYTES = 24 * 1024**3


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def choose_checkpoint(root, retries, tool, sample, image):
    key = hashlib.sha256(sample.encode()).hexdigest() + ".json"
    original_file = root / tool / "checkpoints" / key
    if not original_file.is_file():
        return None
    original = json.loads(original_file.read_text())
    actual, _ = select_retry(original, original_file, retries, tool, sample, image)
    return actual


def verified_source(root, retries, data, sample, tool, image, pair):
    record = real_arm(root, tool, sample, image, pair, retries)
    if record is None or record["status"] != "success":
        return None
    actual = choose_checkpoint(root, retries, tool, sample, image)
    assert actual is not None and not actual["failed"]
    arm = actual["arm"]
    directory = Path(arm["artifact_dir"])
    expected = record["conseq_digest"]
    assert arm["metrics"]["outputs"]["conseq.csv"]["sha256"] == expected
    source = directory / "conseq.csv"
    if digest(source) != expected:
        raise ValueError("source-attested physical MiCall MAX consensus modified")
    reads = [data / "samples" / sample / f"{sample}_L001_R{i}_001.fastq.gz"
             for i in (1, 2)]
    return source, reads, expected


def run(root, retries, data, cache, micall, images_file,
        witness, attestation, max_new, requested=None):
    root, data, cache = Path(root), Path(data), Path(cache)
    if max_new < 0 or cache == root or cache.is_relative_to(root):
        raise ValueError("unsafe sidecar location or negative new-item count")
    if cache == data or cache.is_relative_to(data):
        raise ValueError("sidecars must be separate from original FASTQs")
    if digest(images_file) != IMAGE_MANIFEST:
        raise ValueError("immutable seven-image manifest changed")
    if digest(Path(micall) / "micall/utils/exact_coverage.py") != EXACT_MODULE:
        raise ValueError("MiCall exact-coverage module changed")
    from .exact_backfill import generate_one, unavailable_report

    images = json.loads(Path(images_file).read_text())
    pairs = physical_pairs(witness, attestation)
    if requested is not None and not set(requested) <= set(pairs):
        raise ValueError("physical sample absent from attested witness")
    ordered = sorted(pairs, key=lambda name: (
        sum(int(entry["bytes"]) for entry in pairs[name]), name))
    fork = subprocess.check_output(
        ["git", "-C", str(micall), "rev-parse", "HEAD"], text=True).strip()
    counts = {"new": 0, "reused": 0, "failed_arms": 0, "paused": False}
    for sample in ordered:
        if requested is not None and sample not in requested:
            continue
        for tool in ("iva", "haploflow", "megahit",
                     "abyss", "spades", "velvet", "ivanka"):
            source = verified_source(
                root, retries, data, sample, tool, images[tool], pairs[sample])
            if source is None:
                counts["failed_arms"] += 1
                continue
            conseq, fastqs, expected = source
            path = sidecar(cache, "real", sample, tool, candidate=tool)
            report = path / "provenance.json"
            if report.is_file():
                proof = json.loads(report.read_text())
                if proof.get("source_fastq_sha256") != [
                        entry["sha256"] for entry in pairs[sample]]:
                    raise ValueError("reused exact sidecar FASTQ hashes differ")
                generate_one(cache, "real", sample, tool, tool, fastqs,
                             conseq, expected, images[tool], fork)
                counts["reused"] += 1
                continue
            unavailable = path / "unavailable.json"
            if unavailable.exists():
                status = json.loads(unavailable.read_text())
                if (status.get("source_conseq_sha256") != expected
                        or status.get("source_image_sha256") != images[tool]):
                    raise ValueError("unavailable exact sidecar changed")
                counts["unavailable"] = counts.get("unavailable", 0) + 1
                continue
            if counts["new"] >= max_new:
                return counts
            stat = os.statvfs(cache.parent)
            if stat.f_bavail * stat.f_frsize < MIN_FREE_BYTES:
                counts["paused"] = True
                return counts
            if any(digest(file) != pair["sha256"]
                   for file, pair in zip(fastqs, pairs[sample])):
                raise ValueError("original physical reads differ from witness")
            try:
                if generate_one(cache, "real", sample, tool, tool, fastqs,
                                conseq, expected, images[tool], fork):
                    counts["new"] += 1
            except ValueError as error:
                if str(error) != "no final MAX consensus available for exact coverage":
                    raise
                unavailable_report(path, expected, images[tool], error)
                counts["unavailable"] = counts.get("unavailable", 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "retries", "data", "cache", "micall",
                "images-file", "witness", "attestation"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--max-new", type=int, default=2)
    parser.add_argument("--sample", action="append")
    args = parser.parse_args()
    print("EXACT_PHYSICAL_V6_SOURCE_VERIFIED", run(
        args.root, args.retries, args.data, args.cache, args.micall,
        args.images_file, args.witness, args.attestation,
        args.max_new, set(args.sample) if args.sample else None), flush=True)


if __name__ == "__main__":
    main()
