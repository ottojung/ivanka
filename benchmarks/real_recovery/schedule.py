"""Fair bounded resumption of exactly the old failed resource-limited arms."""
import json

from benchmarks.expanded.balanced_dispatch import BalancedQueue, drive
from benchmarks.expanded.comparators_first_real import TOOLS, verify
from .attempt import execute
from .replay import recover


def dispatch(out, original, cases, eligible, images, hxb2, panel, pmm, jobs):
    by_name = {row["sample"]: row for row in cases}
    saved = {tool: recover(out / tool, [by_name[key] for key in eligible[tool]],
                           tool, images[tool], panel, pmm, original)
             for tool in TOOLS}
    all_ids = set(by_name)
    already = {tool: all_ids - eligible[tool] | set(saved[tool])
               for tool in TOOLS}
    queue = BalancedQueue(TOOLS, cases, already,
                          lambda row: row["sample"])
    print("RESOURCE_PHYSICAL_RECOVERED", queue.report(), flush=True)
    journals = {tool: (out / tool / "results.jsonl").open("a", buffering=1)
                for tool in TOOLS}
    try:
        def do(tool, row):
            return execute(row, tool, images, hxb2, panel, pmm, out, original)

        def save(tool, key, record):
            verify(record, by_name[key], tool, images[tool], panel, pmm)
            journals[tool].write(json.dumps(record, sort_keys=True) + "\n")
            print("RESOURCE_PHYSICAL_PROGRESS", tool,
                  queue.report()[tool], flush=True)

        counts = drive(queue, jobs, do, save)
    finally:
        for journal in journals.values():
            journal.close()
    for tool in TOOLS:
        recovered = recover(out / tool, [by_name[key] for key in eligible[tool]],
                            tool, images[tool], panel, pmm, original)
        if len(recovered) != len(eligible[tool]):
            raise ValueError("incomplete physical resource recovery")
    return counts
