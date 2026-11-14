"""Read-only, non-qualifying inventory of v1 execution evidence reusable in v2.

Never relabel an execution, recompute a score, or import a failed arm.
A future qualification runner must independently revalidate every
referenced source before promoting a recorded v1 measurement to v2.
"""
import argparse
import json
import math
from pathlib import Path

from .adapters import ASSEMBLERS
from .hxb2_cohort import attestation
from .micall_checkpoint import digest, existing_case, identity

SCHEMA = "ivanka.expanded.hxb2_v2_case_reuse_inventory.v1"


def same_case(identifier, old_manifest, new_manifest):
    if identifier.startswith("low_depth-s"):
        return False
    for key in ("sha256", "family", "seed", "pairs", "read_length",
                "hxb2_ancestry", "nominal_fractions", "sampled_haplotype_pairs"):
        if old_manifest.get(key) != new_manifest.get(key):
            return False
    return True


def certified_arm(arm, image):
    """An authenticated output may be inventoried, not declared qualified."""
    return (arm.get("status") == "success"
            and arm.get("sha256") == image
            and arm.get("exit_code") == 0
            and type(arm.get("score")) in (int, float)
            and math.isfinite(arm["score"]) and arm["score"] >= 0
            and type(arm.get("seconds")) in (int, float)
            and math.isfinite(arm["seconds"]) and 0 < arm["seconds"] <= 1800
            and arm.get("score_origin") ==
            "micall_final_max_reference_panel_v1"
            and arm.get("timing_origin") == "micall_in_container_monotonic_v1"
            and isinstance(arm.get("final_dominant"), dict)
            and bool(arm["final_dominant"].get("conseq_csv_sha256")))


def attested_image_set(images, source):
    records = source.get("images", {})
    return (isinstance(records, dict)
            and set(records) == set(images) == set(ASSEMBLERS)
            and all(isinstance(records[name], dict)
                    and records[name].get("image_sha256") == image
                    for name, image in images.items()))


def authenticated_clock(arm, clock):
    return (isinstance(clock, dict)
            and clock.get("timing_origin") ==
            "micall_in_container_monotonic_v1"
            and clock.get("exit_code") == 0
            and type(clock.get("seconds")) in (int, float)
            and clock["seconds"] == arm.get("seconds"))


def inventory(original, revised, previous_run, source_attestation):
    original, revised, previous_run = map(
        Path, (original, revised, previous_run))
    proof_v1, proof_v2 = (attestation(original, expected=400),
                          attestation(revised, expected=400))
    if (proof_v1["schema"] != "ivanka.hxb2_truth_validation.v1"
            or proof_v2["schema"] != "ivanka.hxb2_truth_validation.v2"):
        raise ValueError("only source-attested v1 to v2 reuse allowed")
    new_cohort = json.loads((revised / "cohort.json").read_text())
    if new_cohort["source_cohort_sha256"] != proof_v1["cohort_sha256"]:
        raise ValueError("v2 lineage does not match original cohort")
    frozen_file = previous_run / "run_manifest.json"
    frozen = json.loads(frozen_file.read_text())
    images = frozen["images"]
    source_record = json.loads(Path(source_attestation).read_text())
    if (not attested_image_set(images, source_record)
            or frozen.get("cohort_sha256") != proof_v1["cohort_sha256"]
            or frozen.get("truth_proof") != proof_v1
            or frozen.get("fork_attestation_sha256") !=
            digest(source_attestation)
            or set(images) != set(ASSEMBLERS)
            or any(not isinstance(v, str) or len(v) != 64 for v in images.values())):
        raise ValueError("original benchmark source/image evidence mismatch")
    old_cases = {
        x["id"]: x for x in json.loads(
            (original / "cohort.json").read_text())["cases"]
    }
    reuse, needs_new, incomplete = [], [], []
    for new in new_cohort["cases"]:
        name = new["id"]
        if name in new_cohort["changed_read_cases"]:
            needs_new.append(name)
            continue
        old = old_cases[name]
        first, second = (json.loads((root / name / "manifest.json").read_text())
                         for root in (original, revised))
        if (not same_case(name, first, second)
                or old["sha256"] != new["sha256"]
                or digest(original / name / "manifest.json") !=
                digest(revised / name / "manifest.json")):
            raise ValueError("case that claims to be unchanged has drifted")
        row = existing_case(
            previous_run / name, identity(name, first, proof_v1), images)
        if row is None:
            incomplete.append(name)
            continue
        usable, failed = {}, []
        for tool in ASSEMBLERS:
            arm = row["results"][tool]
            if not certified_arm(arm, images[tool]):
                failed.append(tool)
                continue
            folder = previous_run / name / tool
            path = folder / "execution.json"
            clock_file = folder / "timing.json"
            if not clock_file.is_file() or not authenticated_clock(
                    arm, json.loads(clock_file.read_text())):
                raise ValueError("source MiCall timing proof missing or changed")
            usable[tool] = {
                "original_timing_sha256": digest(clock_file),
                "original_execution_sha256": digest(path),
                "image_sha256": images[tool],
                "original_final_conseq_sha256":
                    arm["final_dominant"]["conseq_csv_sha256"],
                "original_score": arm["score"],
                "original_seconds": arm["seconds"],
            }
        reuse.append({
            "case": name, "case_sha256": old["sha256"],
            "original_matrix_sha256": digest(previous_run / name / "matrix.json"),
            "unchanged_input_sha256": row["input_sha256"],
            "successful_evidence": usable, "failed_arms_not_reused": failed,
        })
    return {
        "schema": SCHEMA, "qualification": "NOT_EVALUATED",
        "source_v1_cohort_sha256": proof_v1["cohort_sha256"],
        "target_v2_cohort_sha256": proof_v2["cohort_sha256"],
        "source_run_manifest_sha256": digest(frozen_file),
        "source_image_attestation_sha256": digest(source_attestation),
        "source_image_ids": images, "source_run": str(previous_run),
        "target_changed_cases": needs_new,
        "historical_cases_checked": len(reuse),
        "unstarted_historical_cases": incomplete,
        "successful_arms_candidate_for_reuse":
            sum(len(row["successful_evidence"]) for row in reuse),
        "failed_arms_excluded":
            sum(len(row["failed_arms_not_reused"]) for row in reuse),
        "cases": reuse,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--revised", type=Path, required=True)
    parser.add_argument("--previous-run", type=Path, required=True)
    parser.add_argument("--source-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.original, args.revised, args.previous_run,
                       args.source_attestation)
    with args.output.open("x") as output:
        json.dump(report, output, sort_keys=True, indent=2)
        output.write("\n")
    print("PROVENANCE_REUSE_CANDIDATES",
          report["historical_cases_checked"],
          report["successful_arms_candidate_for_reuse"],
          "NOT_QUALIFIED")


if __name__ == "__main__":
    main()
