"""Authenticate a retry against an original physical failed checkpoint."""
import json
from pathlib import Path

from .hxb2_preview import sha


def source_failure(original):
    if not original["failed"]:
        return False
    arm = original["arm"]
    code, elapsed = arm.get("exit_code"), arm.get("container_wall_seconds", 0)
    if code in (124, 255) and elapsed >= 1790:
        return True
    if code != 247:
        return False
    evidence = Path(arm.get("artifact_dir", "")) / "micall_internal_timing.json"
    return (evidence.is_file()
            and json.loads(evidence.read_text()).get("exit_code") == -9)


def select(original, original_checkpoint, retry_root, tool, name, image):
    if retry_root is None:
        return original, None
    pending = Path(retry_root) / tool / "checkpoints" / original_checkpoint.name
    if not pending.is_file():
        return original, None
    if not source_failure(original):
        raise ValueError("retry attempted an ineligible physical arm")
    record = json.loads(pending.read_text())
    if (record.get("original_checkpoint_sha256") != sha(original_checkpoint)
            or record.get("resource_timeout_seconds") != 3000
            or record.get("sample") != name
            or record.get("tool") != tool
            or record.get("image_id") != image
            or record.get("input_sha256") != original["input_sha256"]
            or record.get("reference_panel_sha256")
            != original["reference_panel_sha256"]
            or record.get("status") != "finished"
            or type(record.get("failed")) is not bool):
        raise ValueError("physical retry is not source-linked")
    return record, {"original_checkpoint_sha256": sha(original_checkpoint),
                    "retry_checkpoint_sha256": sha(pending),
                    "timeout_seconds": 3000, "status": "failed"
                    if record["failed"] else "success"}
