"""Recover original physical Ivanka checkpoints without recomputing success."""
import json

from benchmarks.expanded.comparators_first_real import row_path
from benchmarks.expanded.balanced_dispatch import clear_stale_recovery
from benchmarks.real_recovery.proof import verify


def recover(out, cases, image, panel, pmm):
    base = out / "ivanka"
    records = {}
    for row in cases:
        path = row_path(base, row["sample"])
        if not path.is_file():
            continue
        record = json.loads(path.read_text())
        if record.get("resource_timeout_seconds") != 3000:
            raise ValueError("wrong physical Ivanka resource policy")
        records[row["sample"]] = verify(
            record, row, "ivanka", image, panel, pmm)
    journal = base / "results.jsonl"
    if journal.is_file():
        lines = journal.read_bytes().splitlines(keepends=True)
        saved = [json.loads(line) for line in lines
                 if line.strip() and line.endswith(b"\n")]
        torn = [line for line in lines
                if line.strip() and not line.endswith(b"\n")]
        if (len(torn) > 1 or len(saved) != len({
                row["sample"] for row in saved})
                or any(records.get(row["sample"]) != row for row in saved)):
            raise ValueError("Ivanka journal conflicts with original checkpoints")
    base.mkdir(parents=True, exist_ok=True)
    temp = base / "results.recovered.partial"
    clear_stale_recovery(temp)
    with temp.open("x") as stream:
        for _, record in sorted(records.items()):
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    temp.replace(journal)
    return records
