"""Strict read-only 198-sample qualification for BOTH arms on an updated MiCall base.

Historical milestone198/summary_198 remain unchanged and still attest the
original pinned IVA image. This versioned evaluator requires two fresh, real
MiCall arms with the SAME new base and preserves the identical two numerical
PSI acceptance criteria (final MAX alignment and MiCall in-container runtime).
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from milestone198 import MANIFEST_SHA256, PANEL_SHA256, SAMPLE_COUNT
from psi_acceptance import summarize as summarize_psi


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as inp:
        for data in iter(lambda: inp.read(1024*1024), b""):
            h.update(data)
    return h.hexdigest()


def _finite_positive(value):
    return (type(value) in (int, float)
            and math.isfinite(value) and value > 0)


def verify(records, names, root, iva_image, ivanka_image, source_provenance):
    """Return an audited report with no reconstructed or cached result records."""
    records = list(records)
    names = list(names)
    root = Path(root).resolve()
    report = {
        "schema": "ivanka.new_micall_physical198.v1",
        "samples_expected": SAMPLE_COUNT,
        "samples_found": len(records),
        "valid_pairs": 0,
        "real_data_numeric_gate_pass": False,
        "biological_release_authorized": False,
        "qualification_criteria": ["final_max_alignment", "micall_runtime"],
        "per_sample_alignment_floor": 0.90,
        "per_arm_wall_cap_seconds": 1800,
        "reference_panel_sha256": PANEL_SHA256,
        "reference_panel_count": 33,
        "iva_image": iva_image,
        "ivanka_image": ivanka_image,
        "score_psi": None,
        "time_psi": None,
        "errors": [],
    }
    errors = report["errors"]
    if (len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT):
        errors.append("manifest_not_198_unique")
    if (not isinstance(source_provenance, dict)
            or set(source_provenance) != set(names)
            or any(not isinstance(v, dict) for v in source_provenance.values())):
        errors.append("original_fastq_provenance_not_fully_authenticated")
    if len(records) != SAMPLE_COUNT:
        errors.append("not_198_terminal_rows")
    if len({r.get("sample") for r in records}) != len(records):
        errors.append("duplicate_samples")
    if set(r.get("sample") for r in records) != set(names):
        errors.append("sample_identity_mismatch")
    invocations = {r.get("invocation") for r in records}
    if len(invocations) != 1 or not all(isinstance(x, str) and x for x in invocations):
        errors.append("mixed_or_missing_physical_invocation")
    invitation = next(iter(invocations)) if len(invocations) == 1 else ""
    report["invocation"] = invitation
    deltas_align = []
    deltas_time = []
    for r in records:
        sample = r.get("sample")
        try:
            if r.get("status") != "finished" or r.get("failed") is not False:
                raise ValueError("sample_not_successful")
            if r.get("iva_baseline_reused") is True:
                raise ValueError("not_fresh_both_arm_result")
            if not isinstance(r.get("provenance"), dict):
                raise ValueError("missing_input_provenance")
            if r["provenance"] != source_provenance.get(sample):
                raise ValueError("original_fastq_provenance_mismatch")
            accepted = r["best_contig_acceptance"]
            if (accepted["method"] != "best_final_max_contig_local_alignment_over_reference_panel"
                    or accepted["reference_panel_sha256"] != PANEL_SHA256
                    or accepted["reference_count"] != 33 or accepted["pass"] is not True):
                raise ValueError("reference_panel_or_final_MAX_mismatch")
            pa = accepted["iva_score"]
            pk = accepted["ivanka_score"]
            if not _finite_positive(pa) or not _finite_positive(pk):
                raise ValueError("bad_alignment_scores")
            if pk < 0.90 * pa:
                raise ValueError("alignment_below_90pct_IVA_floor")
            seconds = {}
            for arm, expected_image in (("iva", iva_image), ("ivanka", ivanka_image)):
                x = r[arm]
                if x.get("exit_code") != 0 or x.get("image_id") != expected_image:
                    raise ValueError(arm + "_failed_or_image_mismatch")
                if x.get("timing_origin") != "micall_in_container_monotonic_v1":
                    raise ValueError(arm + "_incompatible_timer")
                duration = x["seconds"]
                wall = x["container_wall_seconds"]
                if (not _finite_positive(duration) or not _finite_positive(wall)
                        or wall > 1800 or duration > wall + 1):
                    raise ValueError(arm + "_time_limit_or_clock_invalid")
                folder = Path(x["artifact_dir"]).resolve()
                expected_folder = (root / invitation / str(sample) / arm).resolve()
                if folder != expected_folder:
                    raise ValueError(arm + "_nonphysical_artifact_location")
                source = folder / "conseq.csv"
                if not source.is_file():
                    source = folder / "scratch" / "conseq.csv"
                source_hash = x["metrics"]["outputs"]["conseq.csv"]["sha256"]
                if not source_hash or file_sha256(source) != source_hash:
                    raise ValueError(arm + "_final_consensus_sha_mismatch")
                seconds[arm] = duration
            deltas_align.append(pk-pa)
            deltas_time.append(seconds["iva"]-seconds["ivanka"])
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            errors.append(str(sample) + ":" + str(exc))
    report["valid_pairs"] = len(deltas_align)
    if errors or len(deltas_align) != SAMPLE_COUNT:
        return report
    try:
        report["score_psi"] = summarize_psi(deltas_align)
        report["time_psi"] = summarize_psi(deltas_time)
    except (ValueError, OverflowError, ArithmeticError) as exc:
        errors.append("psi_unresolved:" + str(exc))
        return report
    report["real_data_numeric_gate_pass"] = all(
        report[key]["positive_all_nonnegative"] for key in ("score_psi", "time_psi"))
    if not report["real_data_numeric_gate_pass"]:
        errors.append("score_or_runtime_signed_power_psi_failed")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_jsonl", type=Path)
    p.add_argument("--fastq-manifest", required=True, type=Path)
    p.add_argument("--fastq-root", required=True, type=Path)
    p.add_argument("--results-root", required=True, type=Path)
    p.add_argument("--iva-image", required=True)
    p.add_argument("--ivanka-image", required=True)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args(argv)
    if file_sha256(a.fastq_manifest) != MANIFEST_SHA256:
        raise ValueError("frozen 198 manifest checksum mismatch")
    fastq_root = a.fastq_root.resolve()
    if a.fastq_manifest.resolve() != fastq_root / "manifest.tsv":
        raise ValueError("manifest must be original FASTQ root manifest.tsv")
    hxb2_path = fastq_root / "hxb2.fasta"
    if not hxb2_path.is_file():
        raise ValueError("original HXB2 reference missing")
    hxb2_sha = file_sha256(hxb2_path)
    with a.fastq_manifest.open() as f:
        manifest_rows = list(csv.DictReader(f, delimiter="\t"))
    names = [row["sample"] for row in manifest_rows]
    if len(names) != SAMPLE_COUNT or len(set(names)) != SAMPLE_COUNT:
        raise ValueError("original manifest is not 198 unique samples")
    source_provenance = {}
    for row in manifest_rows:
        sample = row["sample"]
        if Path(sample).name != sample or sample in (".", ".."):
            raise ValueError("unsafe original FASTQ sample name")
        sample_dir = fastq_root / "samples" / sample
        fastqs = [sample_dir / f"{sample}_L001_R{i}_001.fastq.gz"
                  for i in (1, 2)]
        if any(not path.is_file() for path in fastqs):
            raise ValueError("missing original paired FASTQ for " + sample)
        source_provenance[sample] = {
            "iva_image_id": a.iva_image,
            "hxb2_sha256": hxb2_sha,
            "all_projects": True,
            "fastq_sha256": [file_sha256(path) for path in fastqs],
            "micall_project_code": row.get("micall_project_code", "").strip(),
        }
    with a.results_jsonl.open() as f:
        lines = [json.loads(line) for line in f if line.strip()]
    terminal = [r for r in lines if r.get("status") != "started"]
    from podman_full_micall import image_id, verify_identical_micall_base
    if image_id(a.iva_image) != a.iva_image or image_id(a.ivanka_image) != a.ivanka_image:
        raise ValueError("image references must be real immutable IDs")
    verify_identical_micall_base(a.iva_image, a.ivanka_image)
    report = verify(terminal, names, a.results_root, a.iva_image,
                    a.ivanka_image, source_provenance)
    report["original_fastq_sha256_verified"] = (
        report["valid_pairs"] == SAMPLE_COUNT
        and not any("original_fastq_provenance" in error for error in report["errors"]))
    report["original_hxb2_sha256"] = hxb2_sha
    report["original_fastq_root"] = str(fastq_root)
    report["manifest_sha256"] = MANIFEST_SHA256
    report["results_jsonl_sha256"] = file_sha256(a.results_jsonl)
    report["identical_micall_base_layers_verified"] = True
    report["artifacts_source"] = str(a.results_root.resolve())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x") as out:
        json.dump(report, out, sort_keys=True, indent=2)
        out.write(chr(10))
    print("UPDATED_MICALL_198_PASS" if report["real_data_numeric_gate_pass"]
          else "UPDATED_MICALL_198_NOT_PASSED",
          report["valid_pairs"], "/", SAMPLE_COUNT,
          "errors", len(report["errors"]))
    return 0 if report["real_data_numeric_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
