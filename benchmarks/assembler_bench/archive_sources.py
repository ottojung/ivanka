"""Preserve immutable execution identity independently of derived scores."""
import hashlib
import math
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from .hxb2_preview import COHORT_SHA
from .public_metrics import CATALOG

TOOLS = list(ASSEMBLERS)
SHA = set("0123456789abcdef")


def digest(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def is_hash(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA


def image_evidence(manifest, attestation, path):
    if manifest.get("images") != {
            name: item.get("image_sha256")
            for name, item in attestation.get("images", {}).items()}:
        raise ValueError("archived execution images do not match attestation")
    if manifest.get("fork_attestation_sha256") != digest(path):
        raise ValueError("archived source attestation SHA mismatch")
    if set(manifest["images"]) != set(TOOLS):
        raise ValueError("archived assembler set incomplete")
    src = {}
    for name in TOOLS:
        item = attestation["images"][name]
        commit, image = item.get("source_commit"), item.get("image_sha256")
        if (not isinstance(commit, str) or len(commit) != 40
                or set(commit) - SHA or not is_hash(image)
                or item.get("source_url") !=
                "https://github.com/ottojung/MiCall/tree/" + commit):
            raise ValueError("unverifiable historical image source")
        src[name] = {
            "image_sha256": image, "source_commit": commit,
            "source_url": item["source_url"],
            "source_branch": item.get("source_branch"),
        }
    return {
        "status": "archived", "images": src,
        "base_image_sha256": attestation["base_image_sha256"],
        "attestation_sha256": digest(path),
        "attestation_schema": attestation["schema"],
    }


def run_template(identifier, title, cohort, observed, images, attestation,
                 manifest_file, data_file):
    return {
        "schema": "ivanka.assembler-bench.public.v1",
        "id": identifier, "title": title, "date": "2026-11-13",
        "cohort": cohort, "status": "ineligible",
        "expanded_status": "incomplete", "eligible_for_expanded": False,
        "archive": {
            "schema": "ivanka.assembler-bench.execution-archive.v1",
            "manifest_sha256": digest(manifest_file),
            "results_sha256": digest(data_file),
            "source_attestation_sha256": attestation["attestation_sha256"],
        },
        "expected_sample_count": 400 if cohort == "synthetic" else 198,
        "sample_count": len(observed), "samples": observed,
        "tools": TOOLS, "images": images, "psi": {},
        "score_origin": SCORE_ORIGIN,
        "source_commit": attestation["images"]["iva"]["source_commit"],
        "status_reason": "Completed MiCall executions from this pinned build.",
        "micall_fork_provenance": attestation,
        "timing_origin": "micall_in_container_monotonic_v1",
    }


def diagnostics_from_execution(result):
    source = result.get("diagnostics", {})
    sam = source.get("mapping", {}).get("values", {})
    micall = source.get("micall_csv", {}).get("values", {})
    values = dict(sam)
    values["nuc_soft_clips_count"] = micall.get("soft_clips_count")
    for name in ("nuc_q15_mean_depth", "nuc_q15_covered_fraction",
                 "region_concordance_mean", "final_contig_count",
                 "final_contig_total_bases",
                 "final_contig_31mer_redundancy_fraction"):
        values[name] = micall.get(name)
    return {key: float(v) for key, v in values.items()
            if key in CATALOG and type(v) in (int, float)
            and math.isfinite(v) and v >= 0}
