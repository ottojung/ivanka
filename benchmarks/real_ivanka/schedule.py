"""Run only missing physical Ivanka cases after rehydrating checkpoints."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from benchmarks.real_recovery.proof import verify
from .attempt import execute


def dispatch(out, cases, recovered, image, hxb2, panel, pmm, jobs):
    remaining = [row for row in cases if row["sample"] not in recovered]
    by_name = {row["sample"]: row for row in cases}
    journal = out / "ivanka" / "results.jsonl"
    print("PHYSICAL_IVANKA_RECOVERED", len(recovered), "remaining",
          len(remaining), flush=True)
    with journal.open("a", buffering=1) as log:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            tasks = [pool.submit(execute, row, image, hxb2, panel, pmm, out)
                     for row in remaining]
            for task in as_completed(tasks):
                record = task.result()
                verify(record, by_name[record["sample"]],
                       "ivanka", image, panel, pmm)
                log.write(json.dumps(record, sort_keys=True) + "\n")
                print("PHYSICAL_IVANKA_PROGRESS", len(recovered) + len(
                    remaining) - sum(not t.done() for t in tasks),
                    "/198", flush=True)
    return len(remaining)
