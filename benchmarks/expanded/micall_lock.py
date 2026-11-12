"""Crash-safe, process-exclusive lock for a long-lived MiCall benchmark."""
from contextlib import contextmanager
import fcntl
from pathlib import Path


@contextmanager
def exclusive_lock(output):
    """Never allow two processes to rewrite the same evidence tree."""
    destination = Path(output).resolve()
    path = destination.with_name(destination.name + ".lock")
    if not path.parent.is_dir():
        raise ValueError("benchmark parent directory must exist")
    with path.open("a+") as descriptor:
        try:
            fcntl.flock(descriptor.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("benchmark already has an active process") from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor.fileno(), fcntl.LOCK_UN)
