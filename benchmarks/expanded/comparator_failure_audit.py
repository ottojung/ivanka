"""Read-only source-attested audit of incomplete six-comparator MiCall runs.

Infrastructure uncertainty remains a failed arm, never an assembler score.
This evaluator may inspect a running journal without altering it or its pods.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from .comparator_first import TOOLS
from .comparator_real_first import validate


def classify(row):
    if row["status"] == "success":
        return "scored_success"
    error = row.get("error") or ""
    info = row.get("micall", {})
    if "Podman wait returned invalid exit status" in error:
        return "unverified_podman_wait"
    if info.get("exit_code") == 124 or "timed out" in error.lower():
        return "timeout"
    if error.startswith("independent post-assembly evaluator:"):
        return "post_micall_evaluation_failure"
    if info.get("exit_code") not in (None, 0):
        return "nonzero_micall_or_container"
    return "unclassified_failed_attempt"


def verify(root):
    """Verify a bounded journal snapshot, not a mutable completion claim."""
    root = Path(root).resolve()
    manifest_file, journal = root / "run_manifest.json", root / "results.jsonl"
    if not manifest_file.is_file() or not journal.is_file():
        raise ValueError("unstarted or unproven comparator real198 cohort")
    manifest_bytes, original = manifest_file.read_bytes(), journal.read_bytes()
    proof = json.loads(manifest_bytes)
    if (proof.get("expected_samples") != 198
            or proof.get("expected_arms") != 1188
            or set(proof.get("images", {})) != set(TOOLS)
            or len(proof.get("original_inputs", {})) != 198
            or proof.get("qualified") is not False):
        raise ValueError("invalid frozen original six-comparator source")
    if original and not original.endswith(b"\n"):
        raise ValueError("journal snapshot interrupted; retry audit")
    records = {}
    for line in original.splitlines():
        row = json.loads(line)
        key = validate(row, proof, root)
        if key in records:
            raise ValueError("duplicate source-asserted comparator arm")
        records[key] = row
    if len(records) > 1188:
        raise ValueError("more arms than original physical cohort")
    return proof, records, {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "journal_sha256": hashlib.sha256(original).hexdigest(),
    }


def summarize(root):
    proof, records, hashes = verify(root)
    by_tool = {}
    for name in TOOLS:
        selected = [r for (_, assembler), r in records.items()
                    if assembler == name]
        breakdown = Counter(classify(row) for row in selected)
        by_tool[name] = {
            "attempted": len(selected),
            "remaining": 198 - len(selected),
            "scored_success": breakdown["scored_success"],
            "failed": sum(v for k, v in breakdown.items()
                          if k != "scored_success"),
            "failure_causes": {key: value for key, value in sorted(
                breakdown.items()) if key != "scored_success"},
        }
    failed = [r for r in records.values() if r["status"] == "failed"]
    return {
        "schema": "ivanka.comparator-real198.read-only-failure-audit.v1",
        "qualified": False,
        "status": "PARTIAL_OR_COMPLETED_ATTEMPTS_NOT_RELEASE_QUALIFICATION",
        "source_commit": proof["source_commit"],
        "expected_arms": 1188, "observed_terminal_arms": len(records),
        "scored_success": sum(v["scored_success"] for v in by_tool.values()),
        "failed_arms": len(failed),
        "remaining_arms": 1188 - len(records),
        "by_tool": by_tool,
        "unverified_podman_exit_samples": sorted(
            f"{r['assembler']}:{r['sample']}" for r in failed
            if classify(r) == "unverified_podman_wait"),
        "failed_arms_are_not_scored_wins": True,
        "raw_inputs_untouched": True,
        "benchmark_journal_untouched": True,
        "source_hashes": hashes,
        "free_bytes_at_snapshot": shutil.disk_usage(root).free,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.results)
    if args.report.exists() or args.report.is_symlink():
        raise ValueError("refusing to overwrite a prior source-bound audit")
    if not args.report.parent.is_dir():
        raise ValueError("audit destination directory does not exist")
    with args.report.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("COMPARATOR_REAL_198_AUDIT", result["observed_terminal_arms"],
          result["scored_success"], result["failed_arms"],
          result["remaining_arms"])


if __name__ == "__main__":
    main()
