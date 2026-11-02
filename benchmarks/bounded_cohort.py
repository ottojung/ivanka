"""Bounded sample scheduler: do not launch new expensive work after strict failure."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


def execute_bounded(rows, jobs, worker, on_start, on_finish, on_error,
                    stop_on_failure=False):
    """Return (records, stopped_early), draining only already-running work.

    A strict cohort cannot pass after any failed sample. Keeping at most
    `jobs` futures in flight prevents an irreversible failure from queuing
    hundreds of unnecessary MiCall containers.
    """
    remaining = iter(rows)
    pending = {}
    records = []
    submitted = 0
    stopped = False

    def submit(executor):
        nonlocal submitted
        try:
            row = next(remaining)
        except StopIteration:
            return False
        on_start(row)
        pending[executor.submit(worker, row)] = row["sample"]
        submitted += 1
        return True

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for _ in range(jobs):
            if not submit(executor):
                break
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                name = pending.pop(future)
                try:
                    record = future.result()
                except Exception as exc:
                    record = on_error(name, exc)
                on_finish(record)
                records.append(record)
                if record.get("failed") is not False and stop_on_failure:
                    stopped = True
            if not stopped:
                while len(pending) < jobs and submit(executor):
                    pass
    return records, stopped and submitted < len(rows)
