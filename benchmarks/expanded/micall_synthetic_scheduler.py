"""Ten-way source-locked MiCall cases, stopping safely when disk is exhausted."""
from concurrent.futures import FIRST_COMPLETED, wait

MIN_AVAILABLE_BYTES = 7 * 1024**3


def execute(pool, cases, jobs, worker, commit, free_bytes):
    """Stream checkpoints without queueing all 400 workloads at once."""
    iterator = iter(cases)
    inflight = set()
    blocked = False

    def fill():
        nonlocal blocked
        while len(inflight) < jobs and not blocked:
            try:
                case = next(iterator)
            except StopIteration:
                return
            if free_bytes() < MIN_AVAILABLE_BYTES:
                blocked = True
                return
            inflight.add(pool.submit(worker, case))

    fill()
    while inflight:
        finished, inflight = wait(inflight, return_when=FIRST_COMPLETED)
        for future in finished:
            commit(future.result())
        fill()
    if blocked:
        raise OSError("checkpointed experiment paused: free workspace below 7 GiB")
