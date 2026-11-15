"""Validate an interrupted source-pinned 198-case cohort as diagnostics only.

Even perfect numerical results here do not certify the required fresh
single-invocation benchmark or the independent expanded 598-case gate.
"""
import argparse
import csv
import json
from pathlib import Path

from benchmarks.assembler_bench.image_source_attestation import verify
from benchmarks.expanded.physical198_recovery_journal import combine, read_journal
from benchmarks.expanded.real_matrix import MANIFEST
from benchmarks.expanded.strict_fork_physical198 import evaluate, sha
from benchmarks.expanded.strict_fork_physical198_evidence import (
    check_retained_arm,
    digest,
    sample_provenance,
)


def audit(original, recovery, dataset, runner, seven, sources, base):
    original, recovery = Path(original), Path(recovery)
    dataset, runner, seven = Path(dataset), Path(runner), Path(seven)
    images_file, attest_file = seven / "images.json", seven / "source-attestation.json"
    images = json.loads(images_file.read_text())
    assert verify(images, attest_file, sources, base) == json.loads(attest_file.read_text())
    old = json.loads((original / "run_manifest.json").read_text())
    new = json.loads((recovery / "run_manifest.json").read_text())
    if (old.get("schema") != "ivanka.bridge-real198.single-invocation.v1"
            or new.get("schema") != "ivanka.fresh-fork-physical198-recovery.v1"
            or old["source_commit"] != new["source_commit"]
            or new.get("qualified") is not False
            or new.get("can_satisfy_single_invocation") is not False
            or images != old["images"] or images != new["images"]
            or new["data_sha256"] != MANIFEST
            or old["real_manifest_sha256"] != MANIFEST
            or old["runner_sha256"] != new["runner_sha256"]
            or new["runner_sha256"] != sha(runner / "benchmarks/podman_full_micall.py")
            or new["source_run_manifest_sha256"] != sha(original / "run_manifest.json")
            or new["reference_attestation_sha256"] != sha(attest_file)
            or old["attestation_sha256"] != sha(attest_file)
            or old["images_sha256"] != sha(images_file)
            or new.get("original_finished_successful") != 169
            or new.get("source_commit") is None):
        raise ValueError("incompatible original/recovery source pins")
    if sha(dataset / "manifest.tsv") != MANIFEST:
        raise ValueError("original physical sample manifest changed")
    with (dataset / "manifest.tsv").open(newline="") as file:
        rows = list(csv.DictReader(file, delimiter="\t"))
    expected = {row["sample"]: row for row in rows}
    if len(rows) != len(expected) or len(expected) != 198:
        raise ValueError("invalid 198 original identities")
    recovered_manifest = json.loads((recovery / "attempt-finished.json").read_text())
    if (recovered_manifest["source_journal_sha256"] != new["source_journal_sha256"]
            or recovered_manifest["run_manifest_sha256"] != sha(recovery / "run_manifest.json")
            or recovered_manifest["recovery_expected"] != 29
            or recovered_manifest["recovered_successes"] != 29
            or recovered_manifest["recovered_failed"] != 0
            or recovered_manifest["recovery_terminal"] != 29
            or recovered_manifest["exit_code"] != 0
            or recovered_manifest["recovery_result_sha256"] !=
            sha(recovery / "results.jsonl")):
        raise ValueError("recovery completion marker invalid")
    before = read_journal(original / "results.jsonl", set(expected))
    after = read_journal(recovery / "results.jsonl", set(expected))
    if (before["sha256"] != new["source_journal_sha256"]
            or len(before["finished"]) != 169
            or len(before["started"]) != 170
            or len(after["finished"]) != 29):
        raise ValueError("source cohort or attested recovery changed")
    missing = set(new["recovery_samples"])
    if missing != set(expected) - set(before["finished"]) or len(missing) != 29:
        raise ValueError("source missing case set differs")
    args = ["--mode", "both", "--jobs", "1", "--parallel-arms",
            "--all-projects", "--timeout-per-arm", "1800",
            "--sample-time-limit", "1800", "--diagnostic-90-floor"]
    for name in [r["sample"] for r in rows if r["sample"] in missing]:
        args.extend(("--sample", name))
    if new.get("args") != args:
        raise ValueError("recovery invocation options differ from pinned source")
    records = combine(before, after, set(expected), missing)
    hxb2 = digest(dataset / "hxb2.fasta")
    for name, record in records.items():
        src = original if name in before["finished"] else recovery
        sample_provenance(name, expected[name], record, dataset, images, hxb2)
        for tool in ("iva", "ivanka"):
            check_retained_arm(name, record, tool, src, images[tool])
    # The real single-invocation verifier additionally rescales final MAX
    # alignments independently; this exploratory aggregate is never a gate.
    diagnostic = evaluate(records, images, set(expected))
    return {
        "schema": "ivanka.physical198.recovery-diagnostic.v1",
        "status": "DIAGNOSTIC_ONLY_NOT_QUALIFIED",
        "release_qualified": False, "single_invocation_qualified": False,
        "expanded_598_qualified": False,
        "source_samples": len(before["finished"]),
        "recovered_samples": len(after["finished"]),
        "numerical_conditions_met_on_recorded_scores": diagnostic["pass"],
        "observed": diagnostic,
        "provenance": {
            "source_journal_sha256": before["sha256"],
            "recovery_journal_sha256": after["sha256"],
            "original_manifest_sha256": MANIFEST,
            "source_run_manifest_sha256": sha(original / "run_manifest.json"),
            "recovery_run_manifest_sha256": sha(recovery / "run_manifest.json"),
            "fork_attestation_sha256": sha(attest_file),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("original", "recovery", "dataset", "runner", "seven",
                "sources", "base", "output"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    result = audit(args.original, args.recovery, args.dataset, args.runner,
                   args.seven, args.sources, args.base)
    with Path(args.output).open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write("\n")
    print(result["status"], result["source_samples"],
          "+", result["recovered_samples"], "!= certified single invocation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
