"""Existing 198x7 original physical checkpoints; no MiCall execution."""
import json
from pathlib import Path

from .frozen_contract import IMAGES


def load(root):
    root = Path(root) / "phase-real198"
    by_tool, sample_set = {}, None
    for name in IMAGES:
        folder = root / name / "checkpoints"
        files = list(folder.glob("*.json"))
        if len(files) != 198:
            raise ValueError("missing original physical cases for " + name)
        rows = {}
        for p in files:
            j = json.loads(p.read_text())
            if (j["tool"] != name or j["status"] != "finished"
                    or j["image_id"] != IMAGES[name]):
                raise ValueError("original case provenance drift: " + name)
            rows[p.stem] = j
        if sample_set is not None and set(rows) != sample_set:
            raise ValueError("physical case identity differs across assemblers")
        sample_set = set(rows)
        by_tool[name] = rows
    return by_tool


def success(record):
    if record["failed"] is not False or not isinstance(record["measurement"], dict):
        return False
    score = record["measurement"].get("score")
    secs = record["measurement"].get("seconds")
    return (isinstance(score, (int, float)) and
            isinstance(secs, (int, float)) and secs > 0)
