"""Parent-owned global admission guard for the ten NONQUALIFYING PX jobs.

Exactly one explorer may hold the global token. Exclusivity is enforced by a
nonblocking ``flock`` on a dedicated lock file, which the kernel releases even
if the holder dies without running Python cleanup. A visible on-disk state
record makes the holder, its reservation and its per-program counters auditable.

Every admission path is fail-closed: an unmeasurable disk, corrupt state, an
already-live holder or any breached cap denies the claim. The token record is
removed on normal exit, on exception and at interpreter exit, and a stale
record from a dead holder is reclaimed when the next claimant arrives.

The guard writes only inside ``GuardConfig.state_dir``. It never opens,
rewrites or deletes frozen MiCall sources, the seven pinned OCI images, the
198/464 case data or any clinical input.
"""
from __future__ import annotations

import atexit
import fcntl
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

FOUNDER_FREE_FLOOR_BYTES = 32 * 1024 ** 3
FOUNDER_INCREMENTAL_CAP_BYTES = 8 * 1024 ** 3
DEFAULT_RESERVATION_BYTES = 1024 ** 3
DEFAULT_MAX_WORKERS = 1
DEFAULT_MAX_WALL_SECONDS = 2400
DEFAULT_MAX_RSS_BYTES = 4_000_000_000
STATE_SCHEMA = "ivanka.px.global-admission.v1"


class AdmissionError(RuntimeError):
    """Base class for every refusal or unsafe guard state."""


class AdmissionDenied(AdmissionError):
    """A claim was refused by policy: busy worker, disk floor or bad state."""


class CapExceeded(AdmissionError):
    """A per-program or global resource cap would be breached."""


class MeasurementUnavailable(AdmissionError):
    """A required measurement could not be taken; the claim fails closed."""


def _pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _du_allocated(path: Path) -> int:
    """Allocated bytes of a dedicated directory, failing closed on error."""
    target = Path(path).resolve()
    if not target.is_dir():
        raise MeasurementUnavailable("missing measured directory: " + str(target))
    result = subprocess.run(
        ["du", "-sB1", "--", str(target)],
        check=True, text=True, capture_output=True, timeout=60,
    )
    return int(result.stdout.split()[0])


def _default_free_bytes(workspace: Path) -> int:
    try:
        stats = os.statvfs(workspace)
    except OSError as exc:
        raise MeasurementUnavailable("cannot measure free disk") from exc
    # f_bavail is the budget available to the non-root user that writes jobs;
    # f_bfree would misleadingly include the ext4 root-reserved blocks.
    return stats.f_bavail * stats.f_frsize


@dataclass
class GuardConfig:
    state_dir: Path
    workspace: Path
    min_free_bytes: int = FOUNDER_FREE_FLOOR_BYTES
    max_incremental_bytes: int = FOUNDER_INCREMENTAL_CAP_BYTES
    reservation_bytes: int = DEFAULT_RESERVATION_BYTES
    max_workers: int = DEFAULT_MAX_WORKERS
    max_wall_seconds: int = DEFAULT_MAX_WALL_SECONDS
    max_rss_bytes: int = DEFAULT_MAX_RSS_BYTES
    per_program_max_bytes: int = FOUNDER_INCREMENTAL_CAP_BYTES
    per_program_max_workers: int = 1
    per_program_max_cost_units: int = 1
    measured_dir: Optional[Path] = None
    free_bytes_fn: Optional[Callable[[Path], int]] = None
    incremental_bytes_fn: Optional[Callable[[], int]] = None
    clock: Callable[[], float] = field(default_factory=lambda: time.time)
    pid_alive: Callable[[int], bool] = field(default_factory=lambda: _pid_alive)

    def __post_init__(self):
        self.state_dir = Path(self.state_dir)
        self.workspace = Path(self.workspace)
        if self.free_bytes_fn is None:
            self.free_bytes_fn = _default_free_bytes
        if self.incremental_bytes_fn is None:
            directory = self.measured_dir
            self.incremental_bytes_fn = (
                (lambda: _du_allocated(directory)) if directory is not None
                else (lambda: 0)
            )
        if (self.min_free_bytes < 0 or self.max_incremental_bytes <= 0
                or self.max_workers < 1 or self.per_program_max_workers < 1
                or self.per_program_max_cost_units < 1):
            raise ValueError("unsafe guard policy")

    @classmethod
    def from_registry(cls, registry_path, *, state_dir, workspace, **kwargs):
        """Bind the guard to the merged explorer registry's founder policy."""
        data = json.loads(Path(registry_path).read_text())
        policy = data["policy"]
        if (policy.get("max_concurrent_exploratory_workers") != DEFAULT_MAX_WORKERS
                or policy.get("min_workspace_free_bytes") != FOUNDER_FREE_FLOOR_BYTES
                or policy.get("total_incremental_storage_bytes") != FOUNDER_INCREMENTAL_CAP_BYTES
                or policy.get("max_container_wall_seconds") != DEFAULT_MAX_WALL_SECONDS
                or policy.get("max_sampled_process_tree_rss_bytes") != DEFAULT_MAX_RSS_BYTES):
            raise AdmissionDenied("registry policy drift vs parent guard constants")
        return cls(state_dir=state_dir, workspace=workspace, **kwargs)


class GlobalAdmissionGuard:
    """Grant at most one fail-closed, time-bounded exploration token."""

    def __init__(self, config: GuardConfig):
        self.config = config
        self.state_dir = config.state_dir
        self.state_path = self.state_dir / "global-admission.json"
        self.lock_path = self.state_dir / ".global-admission.lock"

    def _open_lock(self):
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            return self.lock_path.open("a+")
        except OSError as exc:
            raise AdmissionDenied("guard state/lock directory unavailable") from exc

    def _read_state(self):
        if not self.state_path.exists():
            return {"schema": STATE_SCHEMA, "token": None, "programs": {}}
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError) as exc:
            raise AdmissionDenied("guard state unreadable") from exc
        if (not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA
                or not isinstance(data.get("token"), (dict, type(None)))
                or not isinstance(data.get("programs"), dict)):
            raise AdmissionDenied("guard state schema drift")
        return data

    def _write_state(self, state):
        tmp = self.state_path.with_suffix(".tmp")
        with tmp.open("w") as out:
            json.dump(state, out, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, self.state_path)

    @staticmethod
    def _decrement(counters, active):
        """Remove a token's reservation from a program's counters."""
        counters["workers"] = max(0, int(counters.get("workers", 0)) - 1)
        counters["bytes"] = max(
            0, int(counters.get("bytes", 0)) - int(active.get("reservation_bytes", 0)))
        counters["cost_units"] = max(
            0, int(counters.get("cost_units", 0)) - int(active.get("cost_units", 0)))

    def claim(self, program, *, owner=None, reservation_bytes=None, cost_units=1):
        """Return an ``AdmissionToken`` or raise an ``AdmissionError``.

        The reservation is a pessimistic upper estimate for the next image and
        job; it is checked against both the free-workspace floor and the
        founder's incremental-storage ceiling before any process is spawned.
        """
        if not isinstance(program, str) or not program:
            raise ValueError("program must be a nonempty name")
        if not isinstance(cost_units, int) or cost_units < 1:
            raise ValueError("cost_units must be a positive integer")
        reserve = (self.config.reservation_bytes if reservation_bytes is None
                   else reservation_bytes)
        if not isinstance(reserve, int) or reserve < 1:
            raise ValueError("reservation must be a positive integer")

        handle = self._open_lock()
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise AdmissionDenied("global worker already admitted") from exc

        try:
            state = self._read_state()
            active = state["token"]
            if active is not None:
                if self.config.pid_alive(active.get("pid", -1)):
                    raise AdmissionDenied("global worker already admitted")
                # A dead holder cannot release its own counters; reclaim them.
                stale_program = active.get("program")
                stale = state["programs"].get(stale_program)
                if stale is not None:
                    self._decrement(stale, active)
                    if not any(int(stale.get(k, 0)) for k in
                               ("workers", "bytes", "cost_units")):
                        state["programs"].pop(stale_program, None)

            try:
                free = self.config.free_bytes_fn(self.config.workspace)
                incremental = self.config.incremental_bytes_fn()
            except Exception as exc:
                raise MeasurementUnavailable("resource measurement failed") from exc
            if (not isinstance(free, int) or not isinstance(incremental, int)
                    or free < 0 or incremental < 0):
                raise MeasurementUnavailable("invalid resource measurement")
            if (free < self.config.min_free_bytes
                    or free - reserve < self.config.min_free_bytes):
                raise AdmissionDenied("workspace below founder free-disk floor")
            if incremental + reserve > self.config.max_incremental_bytes:
                raise AdmissionDenied("incremental storage would breach founder ceiling")

            counters = dict(state["programs"].get(program, {}))
            workers = int(counters.get("workers", 0)) + 1
            used_bytes = int(counters.get("bytes", 0)) + reserve
            cost = int(counters.get("cost_units", 0)) + cost_units
            if workers > self.config.per_program_max_workers:
                raise CapExceeded("per-program worker cap")
            if used_bytes > self.config.per_program_max_bytes:
                raise CapExceeded("per-program disk cap")
            if cost > self.config.per_program_max_cost_units:
                raise CapExceeded("per-program cost cap")
            total_workers = sum(
                int(v.get("workers", 0)) for v in state["programs"].values())
            if total_workers + 1 > self.config.max_workers:
                raise CapExceeded("global worker cap")

            token_id = uuid.uuid4().hex
            state["token"] = {
                "id": token_id,
                "program": program,
                "owner": owner or program,
                "pid": os.getpid(),
                "claimed_utc": self.config.clock(),
                "reservation_bytes": reserve,
                "cost_units": cost_units,
                "max_wall_seconds": self.config.max_wall_seconds,
                "max_rss_bytes": self.config.max_rss_bytes,
                "measured_free_bytes": free,
                "measured_incremental_bytes": incremental,
            }
            state["programs"][program] = {
                "workers": workers, "bytes": used_bytes, "cost_units": cost}
            self._write_state(state)
        except Exception:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            raise

        token = AdmissionToken(self, handle, token_id, program, reserve, cost_units)
        atexit.register(_release_at_exit, token)
        return token


def _release_at_exit(token):
    try:
        token.release()
    except AdmissionError:
        pass


class AdmissionToken:
    """Context manager that always releases the global token."""

    def __init__(self, guard, handle, token_id, program, reservation_bytes, cost_units):
        self._guard = guard
        self._handle = handle
        self.id = token_id
        self.program = program
        self.reservation_bytes = reservation_bytes
        self.cost_units = cost_units
        self.released = False

    def __enter__(self):
        if self.released:
            raise AdmissionError("released token cannot be re-entered")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.release()
        except AdmissionError:
            if exc_type is None:
                raise
        return False

    def release(self):
        """Clear the token and its counters; safe to call more than once."""
        if self.released:
            return
        handle = self._handle
        try:
            state = self._guard._read_state()
            active = state["token"]
            if active is not None and active.get("id") == self.id:
                counters = state["programs"].get(self.program)
                if counters is not None:
                    self._guard._decrement(counters, active)
                    if not any(int(counters.get(k, 0)) for k in
                               ("workers", "bytes", "cost_units")):
                        state["programs"].pop(self.program, None)
                state["token"] = None
                self._guard._write_state(state)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            self.released = True
