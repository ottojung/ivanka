"""Post-execution, reference-blind extraction of final-MAX diagnostics.

A terminal successful PX receipt is the only admission ticket. This module
reads retained MiCall artifacts, validates the source-pinned exact-coverage
provenance and writes an attested diagnostics record. Every metric is either
extracted with attested evidence or carries an explicit unavailable reason;
silent nulls are never treated as complete. It never launches MiCall, never
opens truth or a reference, and never ranks a contig by a benchmark score.
"""
import csv
import hashlib
import math
from pathlib import Path

from benchmarks.diagnostic_metrics import extract as extract_canonical

from . import exact_cache
from . import px_cohort_scheduler as sched
from .metric_catalog_exact import values as exact_values

SCHEMA = "ivanka.px.diagnostics.v3"
OVERLAP_SIZE = 70
TRACKS = ("exact_coverage", "exact_coverage_overlapped")
METHOD = "micall-longest-final-MAX-exact-v2"
METRICS = ("final_max", "canonical_micall", "exact_coverage")
EXTRACTED = "extracted"
UNAVAILABLE = "unavailable"


def final_max(output_dir):
    """Locate the frozen final MAX consensus artifact, never a raw contig."""
    root = Path(output_dir)
    for candidate in (root / sched.MAX_ARTIFACT,
                      root / "scratch" / sched.MAX_ARTIFACT):
        if candidate.is_file():
            return candidate
    return None


def _metric(status, reason=None, values=None, evidence=None):
    """Every metric carries an explicit extracted/unavailable state."""
    if status not in (EXTRACTED, UNAVAILABLE):
        raise ValueError("metric status must be extracted or unavailable")
    if status == UNAVAILABLE and not isinstance(reason, str):
        raise ValueError("unavailable metric requires an explicit reason")
    if status == EXTRACTED and reason is not None:
        raise ValueError("extracted metric may not carry an unavailable reason")
    record = {"status": status, "unavailable_reason": reason}
    if values is not None:
        record["values"] = values
    if evidence is not None:
        record["evidence"] = evidence
    return record


def _unavailable(reason):
    return _metric(UNAVAILABLE, reason=reason)


def _assert_fastqs(fastq_sha256):
    reads = list(fastq_sha256)
    if len(reads) != 2 or any(not isinstance(value, str)
                               or not sched.SHA256.fullmatch(value)
                               for value in reads):
        raise ValueError("exact coverage requires two attested FASTQ SHA-256s")
    return reads


def _write_attested(path, obj):
    """Publish an immutable JSON record with a matching SHA-256 sidecar."""
    target = Path(path)
    data = sched._json_bytes(obj)
    digest = hashlib.sha256(data).hexdigest()
    if target.is_file():
        if sched.sha256_file(target) != digest:
            raise ValueError("immutable diagnostics record changed")
    else:
        sched._atomic_write(target, data)
    sidecar = Path(str(target) + ".sha256")
    if sidecar.is_file():
        if sidecar.read_text().strip() != digest:
            raise ValueError("immutable diagnostics record changed")
    else:
        sched._atomic_write(sidecar, (digest + "\n").encode())
    return target, digest


def _final_max_metric(artifact, output_sha256):
    with Path(artifact).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    max_rows = [row for row in rows
                if row.get("consensus-percent-cutoff") == "MAX"]
    sequences = [(row.get("sequence") or "").upper() for row in max_rows]
    lengths = [len(seq) for seq in sequences if seq]
    evidence = {"output_sha256": output_sha256, "row_count": len(max_rows)}
    return _metric(EXTRACTED, values={
        "rows": len(max_rows), "sequence_count": len(lengths),
        "total_bases": sum(lengths), "longest_bases": max(lengths, default=0),
    }, evidence=evidence), lengths


def _canonical_metric(output_dir):
    """Reuse canonical MiCall diagnostic extraction; never guess columns."""
    report = extract_canonical(Path(output_dir))
    values = report.get("values") or {}
    unavailable = sorted(report.get("unavailable") or [])
    errors = list(report.get("errors") or [])
    if errors:
        return _unavailable("canonical diagnostics extraction error: " + errors[0])
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return _unavailable("no canonical MiCall diagnostics available")
    return _metric(EXTRACTED, values=present, evidence={
        "unavailable": unavailable,
        "qualification_effect": report.get("qualification_effect"),
    })


def validate_exact_report(report, output_sha256, fastq_sha256):
    """Fail closed unless an exact-coverage report is source-pinned and bound."""
    if not isinstance(report, dict):
        raise TypeError("exact-coverage report is not an object")
    reads = _assert_fastqs(fastq_sha256)
    if (report.get("method") != METHOD
            or report.get("source_conseq_sha256") != output_sha256
            or not isinstance(report.get("source_image_sha256"), str)
            or not sched.SHA256.fullmatch(report["source_image_sha256"])
            or report.get("overlap_size") != OVERLAP_SIZE
            or report.get("micall_exact_coverage_module_sha256")
            != exact_cache.SOURCE_SHA256
            or report.get("source_fastq_sha256") != reads
            or report.get("exact_coverage_sha256")
            != sched.sha256_file(report.get("exact_coverage_csv", ""))):
        raise ValueError("exact-coverage source provenance disagrees")
    tracks = report.get("tracks")
    if not isinstance(tracks, dict) or any(track not in tracks for track in TRACKS):
        raise ValueError("exact-coverage report lacks both tracks")
    metrics = exact_values(report)
    if any(type(value) not in (int, float) or not math.isfinite(value)
           or value < 0 for value in metrics.values()):
        raise ValueError("invalid exact-coverage aggregates")
    return metrics


def _exact_metric(report, output_sha256, fastq_sha256, lengths):
    if not lengths:
        return _unavailable("no final MAX consensus sequence in conseq.csv")
    if report is None:
        return _unavailable("exact coverage report not provided")
    if isinstance(report, dict) and report.get("status") == "unavailable":
        reason = report.get("unavailable_reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("unavailable exact report lacks an explicit reason")
        return _unavailable(reason)
    reads = _assert_fastqs(fastq_sha256)
    if not isinstance(report, dict):
        raise TypeError("exact-coverage report is not an object")
    if (report.get("method") != METHOD
            or report.get("source_conseq_sha256") != output_sha256
            or not isinstance(report.get("source_image_sha256"), str)
            or not sched.SHA256.fullmatch(report["source_image_sha256"])
            or report.get("overlap_size") != OVERLAP_SIZE
            or report.get("micall_exact_coverage_module_sha256")
            != exact_cache.SOURCE_SHA256
            or report.get("source_fastq_sha256") != reads):
        raise ValueError("exact-coverage source provenance disagrees")
    csv_path = report.get("exact_coverage_csv")
    csv_sha = report.get("exact_coverage_sha256")
    if not isinstance(csv_sha, str) or not sched.SHA256.fullmatch(csv_sha):
        raise ValueError("exact-coverage CSV sha256 is required")
    if (csv_path is not None
            and (not Path(csv_path).is_file()
                 or sched.sha256_file(csv_path) != csv_sha)):
        raise ValueError("exact-coverage CSV does not match provenance")
    tracks = report.get("tracks")
    if not isinstance(tracks, dict) or any(track not in tracks for track in TRACKS):
        raise ValueError("exact-coverage report lacks both tracks")
    metrics = exact_values(report)
    if any(type(value) not in (int, float) or not math.isfinite(value)
           or value < 0 for value in metrics.values()):
        raise ValueError("invalid exact-coverage aggregates")
    return _metric(EXTRACTED, values=metrics, evidence={
        "implementation_sha256": exact_cache.SOURCE_SHA256,
        "method": METHOD, "overlap_size": OVERLAP_SIZE,
        "exact_coverage_sha256": csv_sha,
        "source_fastq_sha256": reads,
    })


def _validate(diagnostics):
    metrics = diagnostics.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
        raise ValueError("diagnostics metrics are incomplete")
    for name, metric in metrics.items():
        if not isinstance(metric, dict):
            raise TypeError("metric record is not an object: " + name)
        status = metric.get("status")
        reason = metric.get("unavailable_reason")
        if status == UNAVAILABLE and not isinstance(reason, str):
            raise ValueError("metric lacks explicit unavailable reason: " + name)
        if status == EXTRACTED and reason is not None:
            raise ValueError("extracted metric has unavailable reason: " + name)
        if status not in (EXTRACTED, UNAVAILABLE):
            raise ValueError("unknown metric status: " + name)
    sched._assert_public(diagnostics)
    return diagnostics


def extract(root, arm, output_dir, *, fastq_sha256, exact_report=None):
    """Return attested diagnostics for one terminal successful PX arm."""
    receipt = sched.verify_receipt(root, arm)
    if receipt is None or receipt["outcome"] != "success":
        raise ValueError("diagnostics require a terminal successful receipt")
    artifact = final_max(output_dir)
    if (artifact is None
            or sched.sha256_file(artifact) != receipt["output_sha256"]):
        raise ValueError("final MAX output is missing or changed since receipt")
    reads = _assert_fastqs(fastq_sha256)
    expected = receipt["input_sha256"]
    if reads != [expected.get("R1"), expected.get("R2")]:
        raise ValueError("diagnostic FASTQ hashes differ from terminal receipt")
    final_metric, lengths = _final_max_metric(artifact, receipt["output_sha256"])
    diagnostics = {
        "schema": SCHEMA, "tool_id": arm["tool_id"], "cohort": arm["cohort"],
        "alias": arm["alias"], "source_commit": arm["source_commit"],
        "adapter_commit": arm["adapter_commit"],
        "image_sha256": arm["image_sha256"],
        "output_sha256": receipt["output_sha256"],
        "seconds": receipt["seconds"],
        "peak_rss_bytes": receipt["peak_rss_bytes"],
        "runner_receipt_sha256": receipt.get("runner_receipt_sha256"),
        "metrics": {
            "final_max": final_metric,
            "canonical_micall": _canonical_metric(output_dir),
            "exact_coverage": _exact_metric(report=exact_report,
                                            output_sha256=receipt["output_sha256"],
                                            fastq_sha256=reads, lengths=lengths),
        },
    }
    return _validate(diagnostics)


def diagnostics_complete(record):
    """Complete means every metric is extracted or explicitly unavailable."""
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return False
    try:
        _validate(record)
    except ValueError:
        return False
    return True


def record(root, arm, output_dir, *, fastq_sha256, exact_report=None):
    """Write and hash-attest the diagnostics record for one arm."""
    diagnostics = extract(root, arm, output_dir,
                          fastq_sha256=fastq_sha256, exact_report=exact_report)
    path = Path(root) / "diagnostics" / (sched.receipt_id(arm) + ".json")
    return _write_attested(path, diagnostics)
