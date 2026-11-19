"""Conservative, no-rerun qualification of historical benchmark evidence."""
from pathlib import Path
import hashlib

MAX_WALL = 2400
MAX_RSS = 4_000_000_000


def container_name(record):
    arm = record.get("arm") or {}
    folder = arm.get("artifact_dir")
    if not isinstance(folder, str) or not folder:
        return None
    invocation = Path(folder).parent.parent.name
    if not invocation:
        return None
    arm_name = "iva" if record.get("tool") == "iva" else "ivanka"
    sample = record.get("sample")
    if not isinstance(sample, str) or not sample:
        return None
    suffix = hashlib.sha256(sample.encode()).hexdigest()[:8]
    return f"ivanka-bench-{arm_name}-{invocation}-{suffix}"


def category(record, peak_rss, audit):
    """Never promote an old uncapped success to a verified hard-limit pass."""
    if record.get("failed") is True:
        return "failed"
    arm = record.get("arm") or {}
    wall = arm.get("container_wall_seconds")
    if not isinstance(wall, (int, float)) or wall < 0:
        return "invalid_runtime"
    if wall > MAX_WALL:
        return "over_40_minutes"
    if peak_rss is None:
        return "memory_unmeasured"
    if peak_rss > MAX_RSS:
        return "observed_over_4GB"
    if audit is None:
        return "legacy_uncapped"
    if (audit.get("memory_max_bytes") != MAX_RSS
            or audit.get("podman_timeout_seconds", 9999) > MAX_WALL - 2):
        return "invalid_cap_audit"
    return "observed_within_budget_not_kernel_proven"
