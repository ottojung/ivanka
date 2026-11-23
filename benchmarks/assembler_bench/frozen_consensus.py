"""Check original scientific output bytes, not only the 4,634 result receipts."""
import json
from pathlib import Path

from .frozen_contract import IMAGES, sha


def verified(root, source, expected):
    target = Path(source).resolve(strict=True)
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError("original consensus is outside the frozen archive")
    if (not isinstance(expected, str) or len(expected) != 64
            or sha(target) != expected):
        raise ValueError("original consensus bytes differ from signed evidence")


def attest_outputs(root):
    root = Path(root)
    real, synth = 0, 0
    for tool in IMAGES:
        for checkpoint in (root / "phase-real198" / tool / "checkpoints").glob("*.json"):
            record = json.loads(checkpoint.read_text())
            if record["failed"]:
                continue
            arm = record["arm"]
            expected = arm["metrics"]["outputs"]["conseq.csv"]["sha256"]
            verified(root, Path(arm["artifact_dir"]) / "conseq.csv", expected)
            real += 1
    cases = [p for p in (root / "phase-synthetic464").iterdir() if p.is_dir()]
    for case in cases:
        for tool in IMAGES:
            record = json.loads((case / tool / "execution.json").read_text())
            if record["status"] != "success":
                continue
            expected = record["final_dominant"]["conseq_csv_sha256"]
            verified(root, case / tool / "conseq.csv", expected)
            synth += 1
    if real != 1148 or synth != 3043:
        raise ValueError("original scientific output count changed")
    return {"physical_success_conseq_sha_verified": real,
            "synthetic_success_conseq_sha_verified": synth}
