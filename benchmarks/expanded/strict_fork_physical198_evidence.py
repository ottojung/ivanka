"""Independently authenticate retained fresh physical MiCall evidence.

Inputs are the original paired FASTQs, not a substituted benchmark cache.
Outputs are actual post-MiCall files, not fields copied from a results journal.
"""
import csv
import hashlib
import json
from pathlib import Path

TIMING = "micall_in_container_monotonic_v1"


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sample_provenance(sample, row, record, dataset, images, hxb2_sha):
    if not sample or Path(sample).name != sample or sample in (".", ".."):
        raise ValueError("unsafe sample identifier")
    if record.get("sample") != sample or record.get("hxb2_sha256") != hxb2_sha:
        raise ValueError("wrong sample or HXB2 provenance")
    if record.get("sample_time_limit_seconds") != 1800:
        raise ValueError("changed physical 1800-second sample cap")
    if record.get("iva_baseline_reused") is not None:
        raise ValueError("non-fresh IVA control flag")
    if record.get("baseline_error") or record.get("evaluation_error"):
        raise ValueError("reported baseline or evaluation error")
    original = Path(dataset) / "samples" / sample
    fastqs = [original / f"{sample}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    if not all(p.is_file() and p.stat().st_size > 0 for p in fastqs):
        raise ValueError("original paired FASTQ unavailable")
    expected = {
        "iva_image_id": images["iva"],
        "hxb2_sha256": hxb2_sha,
        "all_projects": True,
        "fastq_sha256": [digest(f) for f in fastqs],
        "micall_project_code": row.get("micall_project_code", "").strip(),
    }
    if record.get("provenance") != expected:
        raise ValueError("paired FASTQ bytes or MiCall source provenance changed")


def check_retained_arm(sample, record, arm, root, image):
    """Require exact per-invocation output path, timer and final MAX CSV."""
    reported = record[arm]
    invocation = record["invocation"]
    folder = Path(root) / invocation / sample / arm
    if (reported.get("image") != image
            or reported.get("image_id") != image
            or Path(reported.get("artifact_dir", "")) != folder
            or not folder.is_dir() or folder.is_symlink()):
        raise ValueError("retained source-pinned arm directory mismatch")
    files = [folder / name for name in ("micall_internal_timing.json", "conseq.csv")]
    if any(not f.is_file() or f.is_symlink() for f in files):
        raise ValueError("missing or redirected retained MiCall evidence")
    timing = json.loads(files[0].read_text())
    expected = {"exit_code": 0, "seconds": reported["seconds"],
                "timing_origin": TIMING}
    if timing != expected:
        raise ValueError("in-container timing file contradicts the journal")
    metrics = reported["metrics"]
    if not isinstance(metrics, dict):
        raise ValueError("missing retained MiCall metrics")
    outputs = metrics.get("outputs", {})
    conseq = outputs.get("conseq.csv", {})
    if conseq.get("exists") is not True or conseq.get("sha256") != digest(files[1]):
        raise ValueError("retained final MAX consensus hash mismatch")
    with files[1].open(newline="") as file:
        source = list(csv.DictReader(file))
    final = [r["sequence"] for r in source
             if r.get("consensus-percent-cutoff") == "MAX" and r.get("sequence")]
    if (not final or conseq.get("rows") != len(source)
            or metrics.get("num_final_max_conseqs") != len(final)):
        raise ValueError("missing or malformed MiCall final MAX consensus")


def authenticate_records(records, manifest_rows, dataset, root, images):
    """Reject if *any* real sample lacks original input or output proof."""
    dataset = Path(dataset)
    hxb2_sha = digest(dataset / "hxb2.fasta")
    expected = {r["sample"]: r for r in manifest_rows}
    if len(expected) != 198 or set(records) != set(expected):
        raise ValueError("incomplete original physical cohort")
    for sample, record in records.items():
        sample_provenance(sample, expected[sample], record, dataset, images,
                          hxb2_sha)
        for arm in ("iva", "ivanka"):
            check_retained_arm(sample, record, arm, root, images[arm])
    return hxb2_sha
