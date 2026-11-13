"""Count completed authenticated physical-198 MiCall candidate attempts safely."""
import csv
import json
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.real_matrix import MANIFEST
from .hxb2_preview import sha

SCHEMA = "ivanka.expanded.fork_micall_real.v1"
PROGRESS = "ivanka.assembler-bench.real-progress.v1"


def source_ok(manifest, runner):
    sources = manifest.get("source_files_sha256", {})
    required = ("fork_micall_real.py", "real_matrix.py",
                "podman_full_micall.py", "fork_micall_binding.py")
    if set(sources) != set(required):
        raise ValueError("physical-198 benchmark source list changed")
    for name, digest in sources.items():
        root = Path(runner) / "benchmarks"
        path = next((root / part / name for part in ("expanded", "")
                     if (root / part / name).is_file()), None)
        if path is None or sha(path) != digest:
            raise ValueError(f"physical-198 benchmark source mismatch: {name}")


def completed(path, samples, candidate, images):
    if not path.is_file():
        return {"finished": 0, "failed": 0}
    starts, finished = set(), set()
    failures = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        sample, status = event.get("sample"), event.get("status")
        if sample not in samples or status not in ("started", "finished"):
            raise ValueError("unexpected physical sample or event status")
        if status == "started":
            if sample in starts:
                raise ValueError("repeated physical-198 case start")
            starts.add(sample)
            continue
        if sample not in starts or sample in finished:
            raise ValueError("physical-198 finish lacks unique matching start")
        if (event.get("iva", {}).get("image_id") != images["iva"]
                or event.get("ivanka", {}).get("image_id") != images[candidate]
                or type(event.get("failed")) is not bool):
            raise ValueError("physical-198 completed image/outcome not verified")
        finished.add(sample)
        failures += int(event["failed"])
    return {"finished": len(finished), "failed": failures}


def snapshot(root, data, runner, attestation, base, images):
    root = Path(root)
    manifest_file = root / "run_manifest.json"
    manifest = json.loads(manifest_file.read_text())
    selected = set(ASSEMBLERS) - {"iva"}
    if (manifest.get("schema") != SCHEMA or
            manifest.get("expected_samples") != 198 or
            manifest.get("selected_sample") is not None or
            manifest.get("qualified") is not False or
            set(manifest.get("selected_tools", [])) != selected or
            manifest.get("images") != images or
            manifest.get("base_image_sha256") != base or
            manifest.get("fork_attestation_sha256") != sha(attestation) or
            manifest.get("real_manifest_sha256") != MANIFEST or
            sha(Path(data) / "manifest.tsv") != MANIFEST):
        raise ValueError("physical-198 run source / cohort attestation mismatch")
    source_ok(manifest, runner)
    with (Path(data) / "manifest.tsv").open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    samples = {row["sample"] for row in rows}
    if len(rows) != 198 or len(samples) != 198:
        raise ValueError("physical-198 manifest does not contain unique cases")
    candidates = {name: completed(
        root / name / "results.jsonl", samples, name, images)
        for name in sorted(selected)}
    return {"schema": PROGRESS, "expected_samples": 198,
            "status": "incomplete",
            "run_manifest_sha256": sha(manifest_file),
            "candidates": candidates}


def validate_public(report):
    """Enforce aggregate-only, privacy-safe counters on the static site."""
    if report is None:
        return
    import re
    selected = set(ASSEMBLERS) - {"iva"}
    if (set(report) != {"schema", "expected_samples", "status",
                        "run_manifest_sha256", "candidates"}
            or report["schema"] != PROGRESS
            or report["expected_samples"] != 198
            or report["status"] != "incomplete"
            or not re.fullmatch("[0-9a-f]{64}", report["run_manifest_sha256"])
            or set(report["candidates"]) != selected):
        raise ValueError("unsupported or non-anonymous real benchmark progress")
    for name, entry in report["candidates"].items():
        if (set(entry) != {"finished", "failed"}
                or type(entry["finished"]) is not int
                or type(entry["failed"]) is not int
                or not 0 <= entry["failed"] <= entry["finished"] <= 198):
            raise ValueError(f"invalid physical-198 aggregate counts: {name}")
