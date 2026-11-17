"""Dispatch missing synthetic arms evenly while journaling every completion."""
import json

from benchmarks.expanded.balanced_dispatch import BalancedQueue, drive
from benchmarks.expanded.comparators_first_synthetic import TOOLS
from .synthetic_arm import perform
from .synthetic_replay import write_completed


def dispatch(out, cohort, images, proof, results, jobs):
    by_id = {row[0]: row for row in cohort}
    queue = BalancedQueue(
        TOOLS, cohort,
        {tool: {sample for sample, records in results.items()
                if tool in records} for tool in TOOLS},
        lambda row: row[0])
    print("RESOURCE_SYNTHETIC_RECOVERED", queue.report(), flush=True)
    with (out / "results.jsonl").open("a", buffering=1) as journal:
        def do(tool, row):
            return perform(tool, row, out, images)

        def save(tool, key, record):
            results[key][tool] = record
            if len(results[key]) == len(TOOLS):
                row = by_id[key]
                write_completed(out / key, row, proof, results[key])
                completed = json.loads((out / key / "matrix.json").read_text())
                journal.write(json.dumps(completed, sort_keys=True) + "\n")
            print("RESOURCE_SYNTHETIC_RESULT", tool,
                  queue.report()[tool], flush=True)

        return drive(queue, jobs, do, save)
