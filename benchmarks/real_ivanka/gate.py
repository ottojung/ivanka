"""No work until the original six and selective resource recovery complete."""
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_real import TOOLS
from benchmarks.expanded.real_resume import digest


def prerequisites(original, retries, images):
    original, retries = Path(original), Path(retries)
    for root in (original, retries):
        if not (root / "attempt_summary.json").is_file():
            raise ValueError("physical comparator/recovery phase not finished")
    old = json.loads((original / "attempt_summary.json").read_text())
    revised = json.loads((retries / "attempt_summary.json").read_text())
    frozen = json.loads((original / "run_manifest.json").read_text())
    receipt = json.loads((retries / "resource_policy_receipt.json").read_text())
    if (old.get("samples") != 198 or set(old.get("tools", [])) != set(TOOLS)
            or not old.get("ivanka_deferred")
            or old.get("manifest_sha256") != digest(original / "run_manifest.json")
            or revised.get("finished") is not True
            or revised.get("schema") != "ivanka.expanded.physical-resource-retry.v1"
            or revised.get("original") != str(original.resolve())
            or receipt.get("original_run_manifest_sha256")
                != digest(original / "run_manifest.json")
            or receipt.get("original_completed_summary_sha256")
                != digest(original / "attempt_summary.json")
            or receipt.get("timeout_seconds") != 3000
            or frozen.get("expected_samples") != 198
            or frozen.get("ivanka_deferred") is not True
            or frozen.get("images") != {name: images[name] for name in TOOLS}):
        raise ValueError("unattested original physical benchmark completion")
    for tool in TOOLS:
        if len(list((original / tool / "checkpoints").glob("*.json"))) != 198:
            raise ValueError("missing original physical comparator checkpoints")
        eligible = receipt.get("eligibility", {}).get(tool)
        if (not isinstance(eligible, list)
                or revised.get("eligible", {}).get(tool) != len(eligible)
                or len(list((retries / tool / "checkpoints").glob("*.json")))
                   != len(eligible)):
            raise ValueError("incomplete 50-minute comparator recovery")
    return {
        "original_manifest_sha256": digest(original / "run_manifest.json"),
        "original_summary_sha256": digest(original / "attempt_summary.json"),
        "resource_summary_sha256": digest(retries / "attempt_summary.json"),
    }
