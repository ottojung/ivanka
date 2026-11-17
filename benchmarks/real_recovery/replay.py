"""Resume retry checkpoints without ever modifying the original 198 records."""
import json

from benchmarks.expanded.comparators_first_real import row_path, verify
from benchmarks.expanded.balanced_dispatch import clear_stale_recovery
from benchmarks.expanded.real_resume import digest


def recover(folder, rows, tool, image, panel, pmm, original):
    done = {}
    for row in rows:
        key = row["sample"]
        target = row_path(folder, key)
        if not target.is_file():
            continue
        record = json.loads(target.read_text())
        if (record.get("original_checkpoint_sha256") !=
                digest(row_path(original / tool, key))
                or record.get("resource_timeout_seconds") != 3000):
            raise ValueError("retimed physical retry evidence changed")
        verify(record, row, tool, image, panel, pmm)
        done[key] = record
    journal = folder / "results.jsonl"
    if journal.exists():
        lines = journal.read_bytes().splitlines(keepends=True)
        complete = [json.loads(x) for x in lines if x.endswith(b"\n") and x.strip()]
        if len(complete) != len({x["sample"] for x in complete}):
            raise ValueError("duplicate original retry journal rows")
        if any(done.get(x["sample"]) != x for x in complete):
            raise ValueError("physical retry journal disagrees with checkpoints")
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "results.recovered.partial"
    clear_stale_recovery(temp)
    with temp.open("x") as stream:
        for _, record in sorted(done.items()):
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    temp.replace(journal)
    return done
