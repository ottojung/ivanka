"""Ten-way source-locked MiCall cases, stopping safely when disk is exhausted."""
from concurrent.futures import FIRST_COMPLETED, wait

MIN_AVAILABLE_BYTES = 7 * 1024**3


def execute(pool, cases, jobs, worker, commit, free_bytes, reserve_per_arm=0):
    """Checkpoint bounded work; never consume a case under a disk guard."""
    if jobs < 1 or reserve_per_arm < 0:
        raise ValueError("invalid benchmark job count or disk reservation")
    iterator = iter(cases)
    sentinel = object()
    pending = next(iterator, sentinel)
    inflight = set()
    blocked = False

    def fill():
        nonlocal blocked, pending
        while len(inflight) < jobs and pending is not sentinel and not blocked:
            needed = MIN_AVAILABLE_BYTES + reserve_per_arm * (len(inflight) + 1)
            if free_bytes() < needed:
                blocked = True
                return
            case = pending
            pending = next(iterator, sentinel)
            inflight.add(pool.submit(worker, case))

    fill()
    while inflight:
        finished, inflight = wait(inflight, return_when=FIRST_COMPLETED)
        for future in finished:
            commit(future.result())
        fill()
    if blocked and pending is not sentinel:
        raise OSError("checkpointed experiment paused: insufficient free workspace")
