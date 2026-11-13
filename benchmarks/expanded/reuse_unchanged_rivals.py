"""Join separately source-attested Ivanka and unchanged-rival executions."""
import argparse
import json
from pathlib import Path
import subprocess

from benchmarks.assembler_bench.fork_progress import checked as original_checked
from benchmarks.assembler_bench.hxb2_preview import sha
from benchmarks.assembler_bench.image_source_attestation import verify
from .adapters import ASSEMBLERS
from .fork_ivanka_requalification import SCHEMA, check_arm
from .micall_checkpoint import identity

FORMAT = "ivanka.expanded.source_bound_unchanged_rivals.v1"


def new_source_ok(manifest, root):
    for name, digest in manifest["source_sha256"].items():
        candidates = [Path(root)/"benchmarks"/part/name for part in (
            "expanded", "assembler_bench", "")]
        path = next((item for item in candidates if item.is_file()), None)
        if path is None or sha(path) != digest:
            raise ValueError("requalification source differs: " + name)


def rows_from(source):
    text = (Path(source)/"results.jsonl").read_text()
    # A concurrent writer may have a partially appended last line.
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines.pop()
    rows = [json.loads(s) for s in lines if s.strip()]
    if len(rows) != len({r["id"] for r in rows}):
        raise ValueError("duplicate changed-Ivanka case")
    return rows


def join(original, original_runner, original_attestation,
         updated, updated_runner, updated_attestation,
         sources, base, binary_commit):
    """Compute verified overlapping cases; never change either input run."""
    before, prior, original_hash, prior_images = original_checked(
        original, original_runner, original_attestation, sources, base)
    if prior_images["status"] != "SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED":
        raise ValueError("original rival images are not independently attested")
    frozen_file = Path(updated)/"run_manifest.json"
    frozen = json.loads(frozen_file.read_text())
    if (frozen.get("schema") != SCHEMA or frozen.get("qualified") is not False
            or frozen.get("expected") != 400 or frozen.get("limit") is not None
            or frozen["truth_proof"] != before["truth_proof"]
            or frozen["cohort_sha256"] != before["cohort_sha256"]
            or frozen["fork_attestation_sha256"] != sha(updated_attestation)
            or frozen["ivanka_source_commit"] != binary_commit):
        raise ValueError("changed Ivanka experiment source and inputs differ")
    new_att = json.loads(Path(updated_attestation).read_text())
    if (verify(frozen["images"], updated_attestation, sources, base) != new_att
            or new_att["status"] != prior_images["status"]
            or new_att["base_image_sha256"] != prior_images["base_image_sha256"]):
        raise ValueError("changed Ivanka image provenance differs")
    if any(before["images"][name] != frozen["images"][name]
           for name in ASSEMBLERS if name != "ivanka"):
        raise ValueError("rival assembler image changed across the profiles")
    if before["images"]["ivanka"] == frozen["images"]["ivanka"]:
        raise ValueError("updated Ivanka binary identical to previous image")
    new_source_ok(frozen, updated_runner)
    label = subprocess.check_output(
        ["podman", "image", "inspect", "--format",
         '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}',
         frozen["images"]["ivanka"]], text=True, timeout=60).strip()
    if label != binary_commit:
        raise ValueError("updated image does not match Ivanka source commit")
    from benchmarks.assembler_bench.hxb2_preview import pinned_truth
    cohort, proof = pinned_truth()
    identities = {item["id"]:item for item in cohort["cases"]}
    original_rows = {row["id"]:row for row in prior}
    new_rows = rows_from(updated)
    verified = []
    for candidate in new_rows:
        sample = candidate["id"]
        if sample not in identities:
            raise ValueError("updated sample is outside the HXB2 cohort")
        fields = identity(sample, {"family":candidate["family"],
                                  "sha256":identities[sample]["sha256"]}, proof)
        prior_record = original_rows.get(sample)
        if check_arm(Path(updated)/sample, fields,
                     frozen["images"]["ivanka"]) != candidate:
            raise ValueError("changed Ivanka case has modified execution")
        if prior_record is None:
            continue
        if any(prior_record.get(key) != candidate.get(key) for key in fields):
            raise ValueError("case and read identities differ across profiles")
        arms = {name:(candidate["ivanka"] if name == "ivanka" else
                      prior_record["results"][name]) for name in ASSEMBLERS}
        verified.append({
            **fields, "results": arms,
            "arm_evidence": {name:({
                "image_sha256": frozen["images"]["ivanka"],
                "execution_sha256": sha(Path(updated)/sample/"ivanka/execution.json"),
                "source": "changed-ivanka"}
                if name == "ivanka" else {
                "image_sha256": before["images"][name],
                "execution_sha256": sha(
                    Path(original)/sample/name/"execution.json"),
                "source": "unchanged-rival"})
                for name in ASSEMBLERS},
        })
    return {"schema": FORMAT, "status": "incomplete",
            "pass": False, "cohort": "synthetic",
            "expected_cases": 400, "matched_cases": len(verified),
            "original_cases": len(prior), "changed_cases": len(new_rows),
            "rival_execution_manifest_sha256": sha(
                Path(original)/"run_manifest.json"),
            "rival_results_sha256": original_hash,
            "new_execution_manifest_sha256": sha(frozen_file),
            "new_results_sha256": sha(Path(updated)/"results.jsonl"),
            "original_attestation_sha256": sha(original_attestation),
            "new_attestation_sha256": sha(updated_attestation),
            "binary_source_commit": binary_commit,
            "evidence": verified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("original", "original-runner", "original-attestation",
                "updated", "updated-runner", "updated-attestation",
                "sources", "base", "binary-commit", "output"):
        parser.add_argument("--"+arg, required=True)
    options = parser.parse_args()
    result = join(options.original, options.original_runner,
                  options.original_attestation, options.updated,
                  options.updated_runner, options.updated_attestation,
                  options.sources, options.base, options.binary_commit)
    target = Path(options.output)
    with target.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("INDEPENDENTLY_REUSED_UNCHANGED_RIVALS",
          result["matched_cases"], "/400", "changed", result["changed_cases"],
          "original", result["original_cases"],
          "qualified", result["pass"])


if __name__=="__main__":
    main()
