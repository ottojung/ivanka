"""Durable controller liveness and watchdog availability records.

A heartbeat states which lease is being supervised and which live kernel task
writes it. It is not a benchmark result and is never used to claim completion.
The watchdog availability record is what lets admission prove that an
independent observer is running before a new arm may own a container.
"""
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

from . import proc, store
from .errors import GuardExceeded

SCHEMA = "ivanka.watchdog-heartbeat.v1"
ALIVE_SCHEMA = "ivanka.watchdog-alive.v1"
ALIVE_MAX_AGE = 30.0


def path(root, worker):
    """Stable per-lease path; worker ids never become path fragments."""
    digest = hashlib.sha256(str(worker).encode()).hexdigest()[:16]
    return Path(root) / (".watchdog-heartbeat-%s.json" % digest)


def alive_path(root):
    return Path(root) / ".watchdog-alive.json"


def identity(pid, table=None):
    """Identify the emitting task with immutable kernel facts only."""
    table = proc.snapshot() if table is None else table
    record = table.get(int(pid))
    if record is None or any(record.get(key) is None for key in
                             ("starttime", "pid_ns", "cmdline_sha")):
        raise GuardExceeded("binding_unavailable")
    return {"pid": int(pid),
            "fingerprint": [record["starttime"], record["pid_ns"]],
            "cmdline_sha": record["cmdline_sha"]}


def _write(target, event):
    target = Path(target)
    fd, temporary = tempfile.mkstemp(prefix=".heartbeat-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def emit(root, worker, *, pid=None, table=None, cid=None, monotonic=None,
         wall=None, target=None):
    """Write one controller heartbeat atomically with fresh liveness times."""
    found = identity(os.getpid() if pid is None else pid, table)
    event = {"schema": SCHEMA, "lease": str(worker), "pid": found["pid"],
             "fingerprint": found["fingerprint"],
             "cmdline_sha": found["cmdline_sha"], "cid": cid,
             "at_monotonic": (monotonic or time.monotonic)(),
             "at_utc": (wall or time.time)()}
    _write(target or path(root, worker), event)
    return event


class Emitter:
    """Controller-side writer refreshed throughout one bounded arm."""

    def __init__(self, root, worker, *, pid=None, target=None):
        self.root = root
        self.worker = worker
        self.pid = pid
        self.target = target or path(root, worker)
        self.cid = None

    def before_spawn(self):
        """Establish controller identity before any container exists."""
        self.cid = None
        return self.refresh()

    def bound(self, cid):
        """Attach the exact CID once the controller has issued it."""
        self.cid = cid
        return self.refresh()

    def refresh(self):
        return emit(self.root, self.worker, pid=self.pid, cid=self.cid,
                    target=self.target)


def ping(root, *, storage_conf=None, graphroot=None, env=None, pid=None,
         table=None, wall=None, target=None):
    """Advertise readiness only after store and own-identity checks pass.

    A watchdog that cannot see its pinned store or its own kernel identity is
    not observing anything and must not unblock admissions.
    """
    if storage_conf is not None or graphroot is not None:
        pinned = store.pin_env(env, storage_conf=storage_conf)
        store.verify_namespace(pinned, graphroot)
    found = identity(os.getpid() if pid is None else pid, table)
    event = {"schema": ALIVE_SCHEMA, "at_utc": (wall or time.time)(),
             "pid": found["pid"], "fingerprint": found["fingerprint"],
             "cmdline_sha": found["cmdline_sha"], "graphroot": str(graphroot)}
    _write(target or alive_path(root), event)
    return event


def advertise(root, *, storage_conf, graphroot, env=None, **kwargs):
    """Watchdog-only entry point: no readiness without a verified store."""
    if storage_conf is None or graphroot is None:
        raise GuardExceeded("watchdog_unready")
    return ping(root, storage_conf=storage_conf, graphroot=graphroot,
                env=env, **kwargs)


def read_alive(root, *, wall=None, max_age=ALIVE_MAX_AGE, target=None,
               snapshot=None):
    """Refuse readiness that is absent, stale, future-dated or PID-reused."""
    clock = wall if wall is not None else time.time
    source = Path(target or alive_path(root))
    if source.is_symlink() or (source.exists() and not source.is_file()):
        raise GuardExceeded("watchdog_unavailable")
    if not source.exists():
        raise GuardExceeded("watchdog_unavailable")
    try:
        event = json.loads(source.read_text().splitlines()[-1])
        at = float(event["at_utc"]) if isinstance(event, dict) else None
    except (OSError, ValueError, IndexError, TypeError, KeyError) as exc:
        raise GuardExceeded("watchdog_unavailable") from exc
    if not isinstance(event, dict) or event.get("schema") != ALIVE_SCHEMA:
        raise GuardExceeded("watchdog_unavailable")
    if at is None or not math.isfinite(at):
        raise GuardExceeded("watchdog_unavailable")
    age = clock() - at
    if age < 0 or not math.isfinite(age) or age > max_age:
        raise GuardExceeded("watchdog_unavailable")
    if snapshot is not None:
        pid = event.get("pid")
        finger = event.get("fingerprint")
        record = snapshot().get(pid) if isinstance(pid, int) else None
        expected = tuple(finger) if isinstance(finger, list) and len(finger) == 2 else None
        if (record is None or expected is None or expected[0] is None
                or expected[1] is None
                or (record.get("starttime"), record.get("pid_ns")) != expected):
            raise GuardExceeded("watchdog_unavailable")
    return event
