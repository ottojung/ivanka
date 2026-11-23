"""Attest all 4,634 immutable historical MiCall result receipts without runs."""
import hashlib
import json
from pathlib import Path

from .frozen_consensus import attest_outputs
from .frozen_contract import IMAGES, verify_images

INDEX = "854efc35af2811fa8af31eef013fed0fabcb7fe7f69cb012dc934c9fcb97eaa9"


def attest(root, expected=INDEX):
    root = Path(root)
    verify_images(root)
    entries, physical = [], None
    real = root / "phase-real198"
    for tool in sorted(IMAGES):
        files = sorted((real / tool / "checkpoints").glob("*.json"))
        samples = {p.stem for p in files}
        if len(files) != 198 or (physical is not None and physical != samples):
            raise ValueError("frozen physical198 checkpoint set incomplete")
        physical = samples
        for p in files:
            raw = p.read_bytes()
            j = json.loads(raw)
            if (j["tool"] != tool or j["image_id"] != IMAGES[tool]
                    or j["status"] != "finished" or not isinstance(j["failed"], bool)):
                raise ValueError("physical arm provenance changed")
            entries.append(f"real198/{tool}/{p.name} {hashlib.sha256(raw).hexdigest()}\n")
    syn = root / "phase-synthetic464"
    cases = sorted(p.name for p in syn.iterdir() if p.is_dir())
    if len(cases) != 464:
        raise ValueError("frozen synthetic464 sample set incomplete")
    failed = 0
    for case in cases:
        for tool in sorted(IMAGES):
            p = syn / case / tool / "execution.json"
            raw = p.read_bytes()
            j = json.loads(raw)
            if j["sha256"] != IMAGES[tool] or j["status"] not in {"success", "failed"}:
                raise ValueError("synthetic result provenance changed")
            failed += j["status"] == "failed"
            entries.append(f"synthetic464/{case}/{tool}/execution.json "
                           f"{hashlib.sha256(raw).hexdigest()}\n")
    result = hashlib.sha256("".join(sorted(entries)).encode()).hexdigest()
    if len(entries) != 4634 or failed != 205 or result != expected:
        raise ValueError("frozen historical results changed; no reruns permitted")
    verified_outputs = attest_outputs(root)
    return {"physical_arms": 1386, "synthetic_arms": 3248,
            "synthetic_failed_arms": failed, "total": 4634,
            "result_receipt_index_sha256": result, **verified_outputs}
