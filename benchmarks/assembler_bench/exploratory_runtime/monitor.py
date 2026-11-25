"""Continuous best-effort disk/RSS/time monitor; never a filesystem quota.

Pilots and builds use the shared fail-closed guard: identity-bound trees,
null-preserving /proc snapshots, and exact-CID or exact-process-group
teardown. No bare-PID signalling. Kernel hard-cap is never claimed.
"""
import subprocess
import time

from assembler_bench.exploratory_space import admit
from assembler_bench.px_ram_semantics import sampler_fields

from fail_closed_guard import binding, build, proc, teardown
from fail_closed_guard.errors import GuardExceeded
from fail_closed_guard.watch import watch_bound

# Re-exported for legacy callers; one exception type makes the launcher's
# fail-closed handler catch guard reasons from both the legacy sampler and the
# bound watcher.


def attest(observation, *, method=None, version=None, scope=None):
    """Return monitor receipt fields for the sampler that ran.

    The default launcher-process-group sampler observes only the launcher;
    a corrected whole-container sampler must state that scope and version
    explicitly at the call site.
    """
    kwargs = {}
    if method is not None:
        kwargs["method"] = method
    if version is not None:
        kwargs["version"] = version
    if scope is not None:
        kwargs["scope"] = scope
    return sampler_fields(observation, **kwargs)


def rss_group_bytes(pgid):
    result = subprocess.run(["ps", "-eo", "pgid=,rss="], check=True,
                            capture_output=True, text=True, timeout=10)
    return sum(int(fields[1]) * 1024 for line in result.stdout.splitlines()
               if len(fields := line.split()) == 2 and int(fields[0]) == pgid)


def _disk(config, margin, measure, retries=2):
    """Meter disk conservatively; a transiently missing path is not zero bytes.

    Overlay accounting can briefly lose a path while Podman rebuilds a layer.
    Retry a bounded number of times, then fail closed. No missing observation
    is ever replaced with an invented or zero-byte reading.
    """
    for attempt in range(retries + 1):
        try:
            space = measure(config["registry"], config["baseline"], config["root"],
                            config["image_store"], config["workspace"], margin)
            break
        except FileNotFoundError as exc:
            if attempt == retries:
                raise GuardExceeded("measurement_unavailable") from exc
        except GuardExceeded:
            raise
        except ValueError as exc:
            if str(exc) == "exploration would breach disk budget or workspace reserve":
                raise GuardExceeded("disk_limit") from exc
            raise GuardExceeded("measurement_unavailable") from exc
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable") from exc
    if space["incremental_bytes"] + margin > config["budget_bytes"]:
        raise GuardExceeded("disk_limit")
    return space


def _bind_started(proc_handle, cidfile, env, *, start, wall_seconds, interval,
                  clock, sleep, disk, snapshot):
    """Bind the issued CID inside the arm's total wall budget.

    Podman writes --cidfile asynchronously after spawn. Only a transient
    absence of that safe file is retried: launcher exit, a present but bad
    CID, lost init identity or an exhausted deadline are terminal. Every wait
    pass still checks disk accounting and launcher liveness, so the startup
    wait cannot hide a dead job or an admission breach.
    """
    while True:
        remaining = wall_seconds - (clock() - start)
        if remaining <= 0:
            raise GuardExceeded("binding_unavailable")
        disk()
        try:
            cid = binding.read_cid(cidfile)
        except (GuardExceeded, OSError) as exc:
            # A launcher that exited without issuing an identity cannot be
            # waited out. If the file exists but is unsafe or invalid, that is
            # a provenance fault, not a cold-start delay.
            if (proc_handle.poll() is not None
                    or not binding.cidfile_absent(cidfile)):
                raise GuardExceeded("binding_unavailable") from exc
            # Use the configured sampler interval, never an arbitrary fixed
            # sleep, and never wait beyond the arm's own deadline.
            sleep(min(interval, remaining))
            continue
        # A visible CID binds immediately: identity loss is terminal here and
        # is never mistaken for a not-yet-written file.
        return binding.bind_container(cid, env, snapshot=snapshot())


def watch_pilot(proc_handle, config, *, cidfile, env, interval=0.5,
                margin=1024**3, clock=time.monotonic, sleep=time.sleep,
                measure=admit, stop=None, snapshot=None, on_bind=None):
    """Identity-bound PX pilot guard, stopped only by exact CID."""
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    start = clock()

    def take():
        return proc.snapshot() if snapshot is None else snapshot()

    def disk():
        return _disk(config, margin, measure)

    bound = _bind_started(proc_handle, cidfile, env, start=start,
                          wall_seconds=config["wall_seconds"], interval=interval,
                          clock=clock, sleep=sleep, disk=disk, snapshot=take)
    if on_bind is not None:
        # The caller durably records the exact CID at this point, before the
        # launcher can be killed with an unowned container still alive.
        on_bind(bound)

    def terminate(cid):
        if stop is not None:
            return stop(cid)
        return teardown.stop_cid(env, cid)

    return watch_bound(
        bound, limit=config["rss_bytes"], wall_seconds=config["wall_seconds"],
        running=(lambda: proc_handle.poll() is None), snapshot=take,
        measure=disk, stop=terminate, clock=clock, sleep=sleep, interval=interval)


def watch_build(proc_handle, config, *, interval=0.5, margin=1024**3,
                clock=time.monotonic, sleep=time.sleep, measure=admit,
                stop=None, snapshot=None):
    """Launcher-tree guard for builds: no CID, exact process-group teardown."""
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    table = proc.snapshot() if snapshot is None else snapshot()
    if proc_handle.pid not in table:
        # A short build can finish before the monitor attaches. There is no
        # container to reap; prove the exact process group is gone instead of
        # failing closed on an identity that no longer exists.
        proof = build.stop_group(
            {"pid": proc_handle.pid, "pgid": proc_handle.pid}, proc_handle)
        return {"peak_rss": 0, "cid": None, "teardown": proof,
                "enforcement": "userspace_observed", "kernel_enforcement": False}
    bound = build.bind_launcher(proc_handle.pid, snapshot=table)

    def take():
        return proc.snapshot() if snapshot is None else snapshot()

    def terminate(_cid):
        if stop is not None:
            return stop(bound, proc_handle)
        return build.stop_group(bound, proc_handle)

    return watch_bound(
        bound, limit=config["rss_bytes"], wall_seconds=config["wall_seconds"],
        running=(lambda: proc_handle.poll() is None), snapshot=take,
        measure=(lambda: _disk(config, margin, measure)), stop=terminate,
        clock=clock, sleep=sleep, interval=interval, rss_fn=build.rss)


def watch(proc_handle, config, *, interval=1, margin=1024**3,
          clock=time.monotonic, sleep=time.sleep, measure=admit,
          rss=rss_group_bytes, cidfile=None, env=None, stop=None,
          snapshot=None, mode=None, on_bind=None):
    """Legacy sampler for existing callers; bound path for guarded callers."""
    if stop is None:
        stop = config.get("stop")
    bound_cid = config.get("cidfile", cidfile)
    if bound_cid is not None:
        return watch_pilot(proc_handle, config, cidfile=bound_cid,
                           env=config.get("env", env), interval=interval,
                           margin=margin, clock=clock, sleep=sleep,
                           measure=measure, stop=stop, snapshot=snapshot,
                           on_bind=on_bind)
    if mode == "build" or config.get("guard_mode") == "build":
        return watch_build(proc_handle, config, interval=interval, margin=margin,
                           clock=clock, sleep=sleep, measure=measure,
                           stop=stop, snapshot=snapshot)
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    start = clock()
    peak = 0
    while proc_handle.poll() is None:
        if clock() - start >= config["wall_seconds"]:
            raise GuardExceeded("wall_limit")
        space = _disk(config, margin, measure)
        try:
            now = rss(proc_handle.pid)
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable") from exc
        peak = max(peak, now)
        if peak > config["rss_bytes"]:
            raise GuardExceeded("observed_rss_limit")
        if space["incremental_bytes"] + margin > config["budget_bytes"]:
            raise GuardExceeded("disk_limit")
        sleep(interval)
    return peak
