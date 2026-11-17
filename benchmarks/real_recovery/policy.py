"""Pin the 50-minute physical-only rerun selection and benchmark source."""
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_synthetic import atomic
from benchmarks.expanded.real_resume import digest


def receipt(out, original, eligible):
    here = Path(__file__).resolve()
    files = [here, *[here.with_name(name) for name in (
        "runner.py", "attempt.py", "eligibility.py",
        "evidence.py", "replay.py", "schedule.py")],
        *[here.parent / "proof" / name for name in (
            "__init__.py", "arm.py", "record.py")]]
    value = {
        "schema": "ivanka.expanded.physical-resource-retry.v1",
        "original_run_manifest_sha256": digest(original / "run_manifest.json"),
        "original_completed_summary_sha256": digest(original / "attempt_summary.json"),
        "timeout_seconds": 3000, "concurrent_arms": 2,
        "do_not_rerun_original_successes": True,
        "eligibility": {tool: sorted(ids) for tool, ids in eligible.items()},
         "source_sha256": {str(p.relative_to(here.parent)): digest(p)
                          for p in files},
    }
    target = out / "resource_policy_receipt.json"
    if target.exists():
        if json.loads(target.read_text()) != value:
            raise ValueError("physical retry policy source/input changed")
    else:
        atomic(target, value)
