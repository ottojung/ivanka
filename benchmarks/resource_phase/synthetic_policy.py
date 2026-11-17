"""Binding for new resource regime without changing original scientific manifest."""
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_synthetic import atomic
from benchmarks.expanded.micall_checkpoint import digest


def receipt(root):
    files = [Path(__file__).resolve()]
    files.extend(files[0].with_name(name) for name in (
        "synthetic_runner.py", "synthetic_batch.py",
        "synthetic_arm.py", "synthetic_verify.py",
        "synthetic_replay.py", "synthetic_journal.py"))
    value = {
        "schema": "ivanka.expanded.resource-policy.v1",
        "original_run_manifest_sha256": digest(root / "run_manifest.json"),
        "wall_timeout_seconds": 3000, "synthetic_memory_limit_gib": 5,
        "maximum_concurrency": 5,
        "old_1800s_completed_arms_are_preserved": True,
        "source_sha256": {p.name: digest(p) for p in files},
    }
    target = root / "resource_policy_receipt.json"
    if target.exists():
        if json.loads(target.read_text()) != value:
            raise ValueError("resource policy source changed after startup")
    else:
        atomic(target, value)
