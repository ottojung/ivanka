"""Work-conserving dispatch: prefer fewer completed + running cases per assembler.

This is a scheduling preference, not a per-time-step equal-count requirement.
Only one thread owns scheduling state. Each worker owns a distinct (tool, case).
"""
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


def clear_stale_recovery(path):
    """Discard only the old interrupted journal rewrite, never source evidence."""
    pending=Path(path)
    if pending.is_symlink():
        raise ValueError("recovery journal temporary is an unsafe symlink")
    if pending.exists():
        if not pending.is_file():
            raise ValueError("recovery journal temporary is not a file")
        pending.unlink()


class BalancedQueue:
    def __init__(self, tools, items, completed, identifier):
        self.tools = tuple(tools)
        self.inflight = {name: set() for name in self.tools}
        self.finished = {name: set(completed[name]) for name in self.tools}
        self.pending = {}
        self.turn = 0
        values = [(identifier(row), row) for row in items]
        ids = [key for key, _ in values]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark contains duplicate case identifiers")
        for name in self.tools:
            if self.finished[name] - set(ids):
                raise ValueError("replayed checkpoint is not in the cohort")
            self.pending[name] = deque(
                (key, row) for key, row in values
                if key not in self.finished[name])

    def take(self):
        available = [name for name in self.tools if self.pending[name]]
        if not available:
            return None
        count = len(self.tools)
        name = min(available, key=lambda name: (
            len(self.finished[name]) + len(self.inflight[name]),
            len(self.finished[name]),
            (self.tools.index(name) - self.turn) % count))
        self.turn = (self.tools.index(name) + 1) % count
        key, row = self.pending[name].popleft()
        if key in self.inflight[name] or key in self.finished[name]:
            raise ValueError("benchmark duplicate running arm")
        self.inflight[name].add(key)
        return name, key, row

    def complete(self, name, key):
        if key not in self.inflight[name]:
            raise ValueError("completed arm was not scheduled")
        self.inflight[name].remove(key)
        self.finished[name].add(key)

    def report(self):
        return {name: (len(self.finished[name]), len(self.inflight[name]),
                       len(self.pending[name])) for name in self.tools}


def drive(queue, jobs, execute, receive):
    if not 1 <= jobs <= 10:
        raise ValueError("MiCall comparator concurrency must be 1..10")
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        active = {}

        def fill():
            while len(active) < jobs:
                selected = queue.take()
                if selected is None:
                    break
                name, key, row = selected
                active[pool.submit(execute, name, row)] = (name, key)

        fill()
        while active:
            finished, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in finished:
                name, key = active.pop(future)
                record = future.result()
                receive(name, key, record)
                queue.complete(name, key)
            fill()
    return queue.report()
