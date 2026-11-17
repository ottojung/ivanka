"""Prove original physical checkpoints are complete without rescoring successes."""
import json

from benchmarks.expanded.comparators_first_real import TOOLS, row_path, verify


def originals(root, rows, images, panel, pmm):
    if not (root / "attempt_summary.json").is_file():
        raise ValueError("physical original must finish before resource retries")
    summary = json.loads((root / "attempt_summary.json").read_text())
    if summary.get("samples") != 198 or summary.get("ivanka_deferred") is not True:
        raise ValueError("invalid original physical completion")
    original = {}
    for tool in TOOLS:
        folder = root / tool
        journal = folder / "results.jsonl"
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        by_id = {record["sample"]: record for record in records}
        if len(by_id) != 198 or len(records) != 198:
            raise ValueError("original physical checkpoint count changed")
        for row in rows:
            key = row["sample"]
            checkpoint = json.loads(row_path(folder, key).read_text())
            if (checkpoint != by_id[key] or checkpoint["tool"] != tool
                    or checkpoint["input_sha256"] != row["input_sha256"]
                    or checkpoint["image_id"] != images[tool]
                    or checkpoint["status"] != "finished"):
                raise ValueError("original physical checkpoint drift")
            if checkpoint["failed"]:
                verify(checkpoint, row, tool, images[tool], panel, pmm)
        original[tool] = by_id
    return original
