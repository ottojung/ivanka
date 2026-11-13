"""Verify independently timed exact-read-coverage sidecar evidence."""
import hashlib
import json
import math
from pathlib import Path

from .metric_catalog_exact import values

# SHA256 of the exact_coverage.py source in the pinned MiCall fork.
SOURCE_SHA256 = "3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar(cache, cohort, sample, tool, candidate=None):
    token = hashlib.sha256(sample.encode()).hexdigest()
    path = Path(cache) / cohort
    if candidate is not None:
        path = path / candidate
    return path / token / tool


def append(metrics, cache, cohort, sample, tool, source_digest, image,
           candidate=None):
    """Only attach sidecars bound to verified MiCall output and image hashes."""
    result = dict(metrics)
    if cache is None or not source_digest:
        return result, None
    folder = sidecar(cache, cohort, sample, tool, candidate)
    file = folder / "provenance.json"
    coverage = folder / "exact_coverage.csv"
    if not file.is_file() or not coverage.is_file():
        return result, None
    report = json.loads(file.read_text())
    if (report.get("source_conseq_sha256") != source_digest
            or report.get("source_image_sha256") != image
            or report.get("overlap_size") != 70
            or report.get("exact_coverage_sha256") != file_sha256(coverage)
            or report.get("micall_exact_coverage_module_sha256")
            != SOURCE_SHA256
            or report.get("method") != "micall-longest-final-MAX-exact-v2"
            or len(report.get("source_fastq_sha256", [])) != 2
            or any(len(item) != 64 for item in
                   report["source_fastq_sha256"])):
        raise ValueError("exact-coverage sidecar provenance disagrees")
    exact = values(report)
    if any(type(v) not in (int, float) or not math.isfinite(v)
           or v < 0 for v in exact.values()):
        raise ValueError("invalid exact-coverage aggregates")
    result.update(exact)
    plots = {track: list(details["depth_profile"])
             for track, details in report["tracks"].items()}
    return result, {
        "implementation_sha256": report["micall_exact_coverage_module_sha256"],
        "selected_sequence_sha256": report["selected_sequence_sha256"],
        "selected_length": report["bases"],
        "full_span": plots["exact_coverage"],
        "inner_70": plots["exact_coverage_overlapped"],
        "coverage_csv_sha256": report["exact_coverage_sha256"],
    }
