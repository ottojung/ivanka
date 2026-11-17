"""Failures eligible for a different resource budget, not assembler crashes."""
import json
from pathlib import Path


def selected(record):
    if not record["failed"]:
        return False
    arm = record["arm"]
    code = arm.get("exit_code")
    if code == 124:
        return arm.get("container_wall_seconds", 0) >= 1790
    if code == 255:
        return arm.get("container_wall_seconds", 0) >= 1790
    if code == 247:
        path = Path(arm.get("artifact_dir", "")) / "micall_internal_timing.json"
        if not path.is_file():
            return False
        return json.loads(path.read_text()).get("exit_code") == -9
    return False
