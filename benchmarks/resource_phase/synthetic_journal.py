"""Recheck originals before writing any new synthetic checkpoint."""
import json

from benchmarks.expanded.balanced_dispatch import clear_stale_recovery
from .synthetic_replay import completed, prepare


def rehydrate(root, cohort, images, proof):
    recovered = {}
    for row in cohort:
        folder = root / row[0]
        saved = folder / "matrix.json"
        if not saved.exists():
            continue
        old = json.loads(saved.read_text())
        fresh = completed(folder, row, proof, prepare(folder, images))
        if old != fresh:
            raise ValueError("original synthetic case matrix was modified")
        recovered[row[0]] = old
    journal = root / "results.jsonl"
    if journal.exists():
        lines = journal.read_bytes().splitlines(keepends=True)
        records = [json.loads(x) for x in lines
                   if x.endswith(b"\n") and x.strip()]
        torn = [x for x in lines if x and not x.endswith(b"\n")]
        if len(torn) > 1 or len(records) != len({x["id"] for x in records}):
            raise ValueError("duplicate or torn original synthetic journal")
        if any(recovered.get(x["id"]) != x for x in records):
            raise ValueError("original synthetic journal disagrees with cases")
    temp = root / "results.recovered.partial"
    clear_stale_recovery(temp)
    with temp.open("x") as stream:
        for _, record in sorted(recovered.items()):
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    temp.replace(journal)
    return recovered
