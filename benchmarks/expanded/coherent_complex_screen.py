"""Independent complete 16-case four-haplotype coherent-assembly risk screen.

Diagnostic only: fixed HXB2-v2 truth is evaluator-only, not passed to MiCall.
"""
import argparse
import json
import os
from pathlib import Path
import shutil

from benchmarks.expanded import coherent_mixed_screen as parent
from benchmarks.expanded.run_synthetic import cohort_rows

CHECKOUT = Path("/workspace/ivanka-coherent-complex16-20261116")
FAMILY = "complex_mixture"
PARENT_COMMIT = "46c49bdcbabe1d6c99fc3ddb0c6fb3f5de1344ce"


def inputs():
    selected = [(name, folder, meta) for name, folder, meta in
                cohort_rows(parent.DATA) if meta["family"] == FAMILY]
    expected = {f"{FAMILY}-s{i:03d}" for i in range(16)}
    if len(selected) != 16 or {row[0] for row in selected} != expected:
        raise ValueError("expected all 16 source-attested complex-mixture identities")
    return sorted(selected)


def dominance_note(meta):
    nominal = meta["nominal_fractions"]
    observed = meta["sampled_haplotype_pairs"]
    if (len(nominal) != 4 or len(observed) != 4
            or any(type(n) not in (float, int) or not 0 <= n <= 1
                   for n in nominal)
            or any(type(n) is not int or n < 0 for n in observed)
            or sum(observed) != meta["pairs"]):
        raise ValueError("invalid authentic four-haplotype sample counts")
    nominal_max, actual_max = max(nominal), max(observed)
    fixed = nominal.index(nominal_max) if nominal.count(nominal_max) == 1 else None
    majority = observed.index(actual_max) if observed.count(actual_max) == 1 else None
    return {
        "nominal_fractions": nominal,
        "sampled_haplotype_pairs": observed,
        "fixed_truth_index": fixed,
        "observed_pair_majority_index": majority,
        "fixed_truth_not_observed_majority":
            fixed is not None and majority is not None and fixed != majority,
        "technical_chimeric_mates": meta["chimeric_mates"],
        "technical_contamination_pairs": meta["contamination_pairs"],
        "acceptance_score_unchanged": True,
    }


def freeze():
    original = parent.freeze()
    if original["benchmark_runner_commit"] != PARENT_COMMIT:
        raise ValueError("original 32-case diagnostic source changed")
    cases = inputs()
    entries = [
        {"id": name, "manifest_sha256": parent.sha(folder / "manifest.json"),
         "read1_sha256": parent.sha(folder / "reads/R1.fastq.gz"),
         "read2_sha256": parent.sha(folder / "reads/R2.fastq.gz"),
         "dominance_diagnostic": dominance_note(meta)}
        for name, folder, meta in cases
    ]
    return {
        "schema": "ivanka.experimental.coherent_complex16.v1",
        "qualified": False, "release_qualified": False,
        "status": "SOURCE_ATTESTED_DIAGNOSTIC_ONLY",
        "benchmark_runner_commit": parent.commit(CHECKOUT),
        "parent_runner_commit": PARENT_COMMIT,
        "runner_sha256": parent.sha(__file__),
        "native_source_commit": parent.IVANKA_COMMIT,
        "fork_source_commit": parent.FORK_COMMIT,
        "common_micall_commit": parent.COMMON_COMMIT,
        "image_sha256": parent.IMAGE, "common_image_sha256": parent.BASE,
        "source_pilot_manifest_sha256": original["source_pilot_manifest_sha256"],
        "cohort_sha256": original["cohort_sha256"],
        "truth_validation": original["truth_validation"],
        "cases": entries, "max_seconds": 1800,
    }


def run(root):
    frozen = freeze()
    if root.exists():
        saved = json.loads((root / "run_manifest.json").read_text())
        if saved != frozen:
            raise ValueError("source-pinned complex16 resume mismatch")
    else:
        root.mkdir()
        (root / "run_manifest.json").write_text(
            json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    expected = {row["id"]: row for row in frozen["cases"]}
    journal = root / "results.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines()
            if line.strip()] if journal.exists() else []
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate complex-mixture evidence")
    for row in rows:
        name = row["id"]
        if (name not in expected or row["image_sha256"] != parent.IMAGE
                or row["ivanka"] != json.loads(
                    (root / name / "ivanka/execution.json").read_text())):
            raise ValueError("source-pinned prior complex-mixture result changed")
    done = {row["id"] for row in rows}
    for name, folder, meta in inputs():
        if name in done:
            continue
        if shutil.disk_usage("/workspace").free < 8 * 1024**3:
            raise ValueError("disk guard: <8 GiB free")
        item = expected[name]
        if (parent.sha(folder / "manifest.json") != item["manifest_sha256"]
                or parent.sha(folder / "reads/R1.fastq.gz") != item["read1_sha256"]
                or parent.sha(folder / "reads/R2.fastq.gz") != item["read2_sha256"]):
            raise ValueError("original paired read source changed")
        target = root / name
        if target.exists():
            raise ValueError("interrupted unjournaled complex-mixture case")
        target.mkdir()
        print("COMPLEX16_CASE_START", name, flush=True)
        result = parent.attempt((folder, meta), target / "ivanka",
                                "ivanka", parent.IMAGE, 1800)
        with journal.open("a") as stream:
            stream.write(json.dumps({"id": name, "image_sha256": parent.IMAGE,
                                     "ivanka": result}, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        print("COMPLEX16_CASE_RESULT", name, result["status"],
              result.get("score"), flush=True)
    rows = [json.loads(line) for line in journal.read_text().splitlines()
            if line.strip()]
    if len(rows) != 16:
        raise ValueError("complex-mixture screen incomplete")
    marker = {
        "schema": frozen["schema"], "qualified": False,
        "status": "ATTEMPTED_NOT_SEVEN_WAY_QUALIFIED",
        "cases_attempted": 16,
        "failed_arms": sum(row["ivanka"]["status"] != "success" for row in rows),
        "run_manifest_sha256": parent.sha(root / "run_manifest.json"),
        "results_sha256": parent.sha(journal),
    }
    target = root / "attempt-finished.json"
    if target.exists():
        if json.loads(target.read_text()) != marker:
            raise ValueError("complex-mixture completion marker mismatch")
    else:
        target.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")
    print("COMPLEX16_FINISHED_EXPERIMENTAL_ONLY", marker, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args().out)


if __name__ == "__main__":
    main()
