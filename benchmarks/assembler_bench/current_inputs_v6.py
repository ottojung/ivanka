"""Attested partial-arm progress from the current 464-case MiCall synthetic cohort."""
import hashlib
import json
import math
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_checkpoint import digest, reusable_arm
from benchmarks.expanded.micall_dominant import MULTITRUTH_SCORE_ORIGIN
from benchmarks.expanded.score import reference_truths
from .current_inputs import sample, accept
from .hxb2_preview import sha
from .public_case_metrics import synthetic as synthetic_metrics
from .resource_peak import peak_mib, synthetic_name
from .exact_cache import append as exact_metrics

SCHEMA = "ivanka.expanded.fork_micall_synthetic.v1"
COHORT_SHA = "90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4"


def attest(root, data, images, attestation, source):
    root, data, source = Path(root), Path(data), Path(source)
    frozen = json.loads((root / "run_manifest.json").read_text())
    refs = Path(__file__).resolve().parents[1] / "expanded/references"
    proof = json.loads((refs / "mixed-464-v6-validation.json").read_text())
    cohort = json.loads((refs / "mixed-464-v6-cohort.json").read_text())
    if (sha(refs / "mixed-464-v6-cohort.json") != COHORT_SHA
            or sha(data / "cohort.json") != COHORT_SHA
            or frozen.get("schema") != SCHEMA
            or frozen.get("expected") != 464
            or frozen.get("limit") is not None
            or frozen.get("images") != images
            or frozen.get("truth_proof") != proof
            or frozen.get("cohort_sha256") != COHORT_SHA
            or frozen.get("fork_attestation_sha256") != sha(attestation)
            or frozen.get("score_origin") != MULTITRUTH_SCORE_ORIGIN
            or frozen.get("min_abundance") != 0.15
            or cohort.get("samples") != 464):
        raise ValueError("not the source-attested 464-case active MiCall benchmark")
    sources = frozen.get("benchmark_source_sha256", {})
    if not sources:
        raise ValueError("missing versioned benchmark source hashes")
    for name, expected in sources.items():
        paths = [source / "benchmarks" / part / name
                 for part in ("expanded", "expanded/references",
                              "assembler_bench", "")]
        matched = next((path for path in paths if path.is_file()), None)
        if matched is None or sha(matched) != expected:
            raise ValueError("current synthetic scoring source changed: " + name)
    return cohort


def case_sources(data, entry):
    directory = Path(data) / entry["id"]
    if not directory.is_dir():
        raise ValueError("missing frozen synthetic reads for " + entry["id"])
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest.get("family") != entry["id"].rsplit("-s", 1)[0]
            or manifest.get("sha256") != entry["sha256"]
            or manifest.get("score_model_revision") != 2):
        raise ValueError("wrong synthetic case input identity")
    for name, expected in entry["sha256"].items():
        file = (directory / name).resolve()
        if not file.is_relative_to(directory.resolve()) or sha(file) != expected:
            raise ValueError("modified synthetic FASTQ or truth source")
    truths = reference_truths(manifest, directory / manifest["hidden_truth_file"])
    expected_truths = {
        key: (len(sequence), hashlib.sha256(sequence.encode()).hexdigest(),
              manifest["nominal_fractions"][int(key.split("_")[1])])
        for key, sequence in truths}
    if not expected_truths:
        raise ValueError("no required abundant generating truths")
    return expected_truths


def verified_arm(arm_dir, tool, image, truth):
    record = reusable_arm(arm_dir, tool, image, MULTITRUTH_SCORE_ORIGIN)
    if record is None:
        return None
    if record["status"] == "success":
        values = record.get("per_truth")
        if not isinstance(values, dict) or set(values) != set(truth):
            raise ValueError("missing per-abundant-truth MiCall recovery")
        fractions = []
        for name, (length, identity, abundance) in truth.items():
            item = values[name]
            value = item.get("fraction")
            raw = item.get("score")
            if (item.get("length") != length
                    or item.get("truth_sha256") != identity
                    or item.get("nominal_abundance") != abundance
                    or type(value) not in (float, int)
                    or type(raw) not in (float, int)
                    or not math.isfinite(value) or not 0 <= value <= 1
                    or not math.isfinite(raw)
                    or abs(raw / length - value) > 1e-7):
                raise ValueError("changed required-truth recovery evidence")
            fractions.append(value)
        if abs(10000 * sum(fractions) / len(fractions) - record["score"]) > 1e-5:
            raise ValueError("incorrect multi-truth score publication")
    return record


def synthetic(root, data, images, attestation, runner, resources=None,
              exact_root=None):
    manifest = Path(root) / "run_manifest.json"
    if not manifest.exists():
        return {}, None
    cohort = attest(root, data, images, attestation, runner)
    rows = {}
    for index, entry in enumerate(sorted(cohort["cases"], key=lambda c: c["id"]), 1):
        truth = case_sources(data, entry)
        case = Path(root) / entry["id"]
        row = sample(f"H{index:03d}", images, entry["id"].rsplit("-s", 1)[0])
        row["truth_recovery"] = {}
        row["truth_reference"] = {
            name: {"length": length, "sequence_sha256": digest,
                   "nominal_abundance": abundance}
            for name, (length, digest, abundance) in truth.items()}
        for tool in ASSEMBLERS:
            record = verified_arm(case / tool, tool, images[tool], truth)
            if record is None:
                continue
            metrics = synthetic_metrics(record)
            memory = peak_mib(resources or {}, synthetic_name(record))
            if memory is not None:
                metrics["peak_ram_observed_mib"] = memory
            provenance = record.get("final_dominant") or {}
            metrics, profile = exact_metrics(
                metrics, exact_root, "synthetic", entry["id"], tool,
                provenance.get("conseq_csv_sha256"), images[tool])
            if profile is not None:
                row["exact_profiles"][tool] = profile
            accept(row, tool, record, metrics)
            if record["status"] == "success":
                row["truth_recovery"][tool] = {
                    name: round(item["fraction"], 10)
                    for name, item in record["per_truth"].items()}
        if any(row["score"][t] is not None or t in row["failures"] for t in images):
            rows[entry["id"]] = row
    return rows, digest(manifest)
