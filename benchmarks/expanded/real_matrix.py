"""Strictly join independently executed, same-base MiCall comparison arms.

Each tool's contigs enter the same MiCall pipeline via an Ivanka-compatible
reads1/reads2/output wrapper inside a separately pinned image. This converter
does NOT reuse controls or infer missing results; it validates original rows.
"""
import hashlib
import json
from pathlib import Path

from .adapters import ASSEMBLERS

EXPECTED = 198
PANEL = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
MANIFEST = "4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192"


def source_rows(path):
    rows = []
    invocations = set()
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") == "started":
            continue
        rows.append(record)
        invocations.add(record.get("invocation"))
    if len(invocations) != 1 or None in invocations or len(rows) != EXPECTED:
        raise ValueError("requires exactly 198 terminal results from one invocation")
    if len({r.get("sample") for r in rows}) != EXPECTED:
        raise ValueError("missing or duplicate physical samples")
    return {r["sample"]: r for r in rows}


def join_real_runs(specification):
    """Reject control-image drift, missing samples, inconsistent sources/timers."""
    if set(specification) != set(ASSEMBLERS) - {"iva"}:
        raise ValueError("exactly six candidate runs, including Ivanka, required")
    runs = {}
    for tool, spec in specification.items():
        if not isinstance(spec, dict) or len(spec.get("image_id", "")) != 64:
            raise ValueError(f"{tool}: requires pinned image ID")
        runs[tool] = source_rows(spec["results_jsonl"])
    sample_ids = set(runs["ivanka"])
    if any(set(rows) != sample_ids for rows in runs.values()):
        raise ValueError("candidate runs have unequal sample sets")
    generated = []
    for sample in sorted(sample_ids):
        original = runs["ivanka"][sample]
        pinned_iva = original["iva"]["image_id"]
        source_proof = original["provenance"]
        if not isinstance(source_proof, dict) or len(source_proof.get("fastq_sha256", [])) != 2:
            raise ValueError(sample + ": missing two original FASTQ hashes")
        selected = {}
        for name, records in runs.items():
            entry = records[sample]
            candidate, control = entry["ivanka"], entry["iva"]
            eval_result = entry["best_contig_acceptance"]
            # Legacy runner marks a clean tool's run "failed" solely when
            # its score is below its IVA-relative diagnostic floor. That is
            # a legitimate competitor outcome, not a missing measurement.
            expected_failed = not eval_result["pass"]
            if (entry.get("status") != "finished"
                    or entry.get("failed") is not expected_failed
                    or entry.get("baseline_error") is not None
                    or entry.get("evaluation_error") is not None
                    or entry.get("iva_baseline_reused") is True
                    or entry.get("provenance") != source_proof
                    or candidate["image_id"] != specification[name]["image_id"]
                    or control["image_id"] != pinned_iva
                    or eval_result["reference_panel_sha256"] != PANEL
                    or eval_result["method"]
                    != "best_final_max_contig_local_alignment_over_reference_panel"
                    or eval_result["reference_count"] != 33
                    or control.get("timing_origin") != "micall_in_container_monotonic_v1"
                    or candidate.get("timing_origin") != "micall_in_container_monotonic_v1"
                    or control.get("exit_code") != 0
                    or candidate.get("exit_code") != 0):
                raise ValueError(sample + ": invalid pinned physical comparison " + name)
            if (abs(eval_result["iva_score"]
                    - original["best_contig_acceptance"]["iva_score"]) > 1e-9):
                raise ValueError(sample + ": differing IVA consensus across controls")
            if candidate["container_wall_seconds"] > 1800 or control["container_wall_seconds"] > 1800:
                raise ValueError(sample + ": MiCall arm over 1800 seconds")
            selected[name] = {
                "status": "success", "sha256": candidate["image_id"],
                "seconds": candidate["seconds"], "score": eval_result["ivanka_score"],
            }
        selected["iva"] = {
            "status": "success", "sha256": pinned_iva,
            "seconds": original["iva"]["seconds"],
            "score": original["best_contig_acceptance"]["iva_score"],
        }
        fingerprint = hashlib.sha256(
            "".join(source_proof["fastq_sha256"]).encode()).hexdigest()
        generated.append({"id": sample, "cohort": "real",
                          "input_sha256": fingerprint, "results": selected})
    return generated


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_manifest", type=Path,
                        help="JSON map: six tool names to immutable image IDs + results.jsonl")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    matrix = join_real_runs(json.loads(args.run_manifest.read_text()))
    with args.output.open("x") as stream:
        for item in matrix:
            stream.write(json.dumps(item, sort_keys=True)+"\n")
    print(f"VALIDATED_REAL_MATRIX rows={len(matrix)} tools={len(ASSEMBLERS)}")


if __name__ == "__main__":
    main()
