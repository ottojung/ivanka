"""Re-evaluate fresh 198-sample fork-built IVA/Ivanka MiCall comparisons.

This read-only gate never imports cached controls, rewrites evidence, or
substitutes absent runs. Passing does not satisfy the separate 598-case gate.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

from benchmarks.assembler_bench.image_source_attestation import verify
from benchmarks.expanded.real_matrix import MANIFEST, PANEL
from benchmarks.expanded.strict_fork_physical198_evidence import authenticate_records
from psi_acceptance import summarize

SCHEMA = "ivanka.strict_fork_physical198.v1"
TIMING = "micall_in_container_monotonic_v1"
METHOD = "best_final_max_contig_local_alignment_over_reference_panel"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def check_arm(arm, expected):
    if not isinstance(arm, dict):
        raise ValueError("missing arm evidence")
    if (arm.get("image_id") != expected
            or type(arm.get("exit_code")) is not int
            or arm["exit_code"] != 0):
        raise ValueError("invalid pinned arm")
    if arm.get("timing_origin") != TIMING or "metrics" not in arm:
        raise ValueError("missing MiCall timing or metrics")
    runtime, wall = arm.get("seconds"), arm.get("container_wall_seconds")
    if not all(finite(v) and 0 < v <= 1800 for v in (runtime, wall)):
        raise ValueError("invalid arm runtime or 1800-second bound")
    if runtime > wall + 1:
        raise ValueError("in-container timer exceeds container lifetime")
    return runtime


def read_records(path, expected):
    starts, finished, invocations = set(), {}, set()
    raw = Path(path).read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("unterminated execution journal")
    for line in raw.splitlines():
        event = json.loads(line)
        sample, status = event.get("sample"), event.get("status")
        invocation = event.get("invocation")
        if sample not in expected or not invocation:
            raise ValueError("unknown sample or invocation")
        invocations.add(invocation)
        if status == "started":
            if sample in starts:
                raise ValueError("duplicate start")
            starts.add(sample)
        elif status in ("finished", "sample_timeout", "error"):
            if sample not in starts or sample in finished:
                raise ValueError("unmatched or duplicate terminal")
            finished[sample] = event
        else:
            raise ValueError("non-fresh or unrecognized physical event")
    if len(invocations) != 1 or len(starts) != 198 or len(finished) != 198:
        raise ValueError("not one complete 198-sample invocation")
    if starts != expected or set(finished) != expected:
        raise ValueError("wrong physical case set")
    return finished, hashlib.sha256(raw).hexdigest()


def evaluate(records, images, expected):
    """Check every arm, then prove all-r PSI without dropping bad results."""
    report = {"schema": SCHEMA, "pass": False,
              "status": "incomplete", "samples_expected": 198,
              "samples_valid": 0, "floor_failures": 0,
              "invalid_arms": 0, "score_psi": None, "time_psi": None}
    scores, times = [], []
    if set(records) != expected or len(records) != 198:
        return report
    for sample in expected:
        record = records[sample]
        try:
            if record.get("status") != "finished" or record.get("failed") is not False:
                raise ValueError("failed execution")
            if record.get("iva_baseline_reused") is True:
                raise ValueError("imported IVA baseline")
            iva, ivanka = record["iva"], record["ivanka"]
            ta = check_arm(iva, images["iva"])
            tb = check_arm(ivanka, images["ivanka"])
            evidence = record["best_contig_acceptance"]
            if (evidence.get("method") != METHOD
                    or evidence.get("reference_panel_sha256") != PANEL
                    or evidence.get("reference_count") != 33):
                raise ValueError("wrong final MAX panel")
            first, second = evidence.get("iva_score"), evidence.get("ivanka_score")
            if not finite(first) or first <= 0 or not finite(second) or second < 0:
                raise ValueError("nonfinite final MAX score")
            passed = second >= .90 * first
            if evidence.get("pass") is not passed:
                raise ValueError("inconsistent reported per-sample floor")
            if not passed:
                report["floor_failures"] += 1
            elapsed = record.get("total_seconds")
            if not finite(elapsed) or elapsed <= 0:
                raise ValueError("missing sample wall evidence")
            scores.append(second - first)
            times.append(ta - tb)
            report["samples_valid"] += 1
        except (KeyError, ValueError, TypeError, OverflowError):
            report["invalid_arms"] += 1
    if report["invalid_arms"]:
        report["status"] = "invalid-evidence"
        return report
    try:
        report["score_psi"] = summarize(scores)
        report["time_psi"] = summarize(times)
    except ValueError:
        report["status"] = "unresolved-psi"
        return report
    report["pass"] = (not report["floor_failures"]
                      and report["score_psi"]["positive_all_nonnegative"]
                      and report["time_psi"]["positive_all_nonnegative"])
    report["status"] = "passed" if report["pass"] else "failed"
    return report


def qualify(root, dataset, runner, images_path, attestation, sources, base):
    """Authenticate the immutable fork, source, and original 198 inputs."""
    root, dataset, runner = map(Path, (root, dataset, runner))
    images = json.loads(Path(images_path).read_text())
    expected_source = json.loads(Path(attestation).read_text())
    checked = verify(images, attestation, sources, base)
    if checked != expected_source:
        raise ValueError("live seven-image attestation differs")
    manifest = json.loads((root / "run_manifest.json").read_text())
    if (manifest.get("schema") != "ivanka.bridge-real198.single-invocation.v1"
            or manifest.get("images") != images
            or manifest.get("qualified") is not False
            or manifest.get("original_real_samples") != 198
            or manifest.get("real_manifest_sha256") != MANIFEST
            or manifest.get("runner_sha256")
            != sha(runner / "benchmarks/podman_full_micall.py")
            or manifest.get("attestation_sha256") != sha(attestation)
            or manifest.get("images_sha256") != sha(images_path)
            or manifest.get("source_commit") is None
            or manifest.get("runner_args") != [
                "--mode", "both", "--jobs", "1", "--parallel-arms",
                "--all-projects", "--timeout-per-arm", "1800",
                "--sample-time-limit", "1800", "--diagnostic-90-floor"]):
        raise ValueError("physical run source manifest invalid")
    if sha(dataset / "manifest.tsv") != MANIFEST:
        raise ValueError("original real FASTQ manifest changed")
    with (dataset / "manifest.tsv").open(newline="") as file:
        original_rows = list(csv.DictReader(file, delimiter="\t"))
    names = [r["sample"] for r in original_rows]
    if len(names) != 198 or len(set(names)) != 198:
        raise ValueError("original 198 sample IDs changed")
    source = subprocess.check_output(
        ["podman", "image", "inspect", "--format",
         '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}',
         images["ivanka"]], text=True, timeout=60).strip()
    if source != manifest["source_commit"]:
        raise ValueError("native Rust source does not match image")
    records, journal_sha = read_records(root / "results.jsonl", set(names))
    # Rehash original read pairs and actual MiCall artifacts rather than
    # trusting the already-serialized result journal.
    hxb2_sha = authenticate_records(records, original_rows, dataset, root, images)
    report = evaluate(records, images, set(names))
    report["provenance"] = {
        "hxb2_sha256": hxb2_sha,
        "original_reads_and_final_outputs_reverified": True,
        "run_manifest_sha256": sha(root / "run_manifest.json"),
        "result_journal_sha256": journal_sha,
        "attestation_sha256": sha(attestation),
        "original_fastq_manifest_sha256": MANIFEST,
        "source_commit": source,
        "image_id": images["ivanka"],
    }
    report["expanded_seven_way_qualified"] = False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("root", "dataset", "runner", "images", "attestation",
                  "sources", "base", "output"):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    report = qualify(args.root, args.dataset, args.runner, args.images,
                     args.attestation, args.sources, args.base)
    with Path(args.output).open("x") as file:
        json.dump(report, file, sort_keys=True, indent=2)
        file.write("\n")
    print("FRESH_FORK_PHYSICAL198", report["status"], report["samples_valid"],
          "/198; expanded benchmark still pending", flush=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
