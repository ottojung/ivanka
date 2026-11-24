"""Continuous best-effort disk/RSS/time monitor; never a filesystem quota.

Pilots and builds use the shared fail-closed guard: identity-bound trees,
null-preserving /proc snapshots, and exact-CID or exact-process-group
teardown. No bare-PID signalling. Kernel hard-cap is never claimed.
"""
import subprocess
import time

from assembler_bench.exploratory_space import admit

from fail_closed_guard import binding, build, proc, teardown
from fail_closed_guard.watch import watch_bound


class GuardExceeded(Exception):
    pass


def rss_group_bytes(pgid):
    result = subprocess.run(["ps", "-eo", "pgid=,rss="], check=True,
                            capture_output=True, text=True, timeout=10)
    return sum(int(fields[1]) * 1024 for line in result.stdout.splitlines()
               if len(fields := line.split()) == 2 and int(fields[0]) == pgid)


def _disk(config, margin, measure):
    try:
        space = measure(config["registry"], config["baseline"], config["root"],
                        config["image_store"], config["workspace"], margin)
        if space["incremental_bytes"] + margin > config["budget_bytes"]:
            raise GuardExceeded("disk_limit")
        return space
    except GuardExceeded:
        raise
    except ValueError as exc:
        if str(exc) == "exploration would breach disk budget or workspace reserve":
            raise GuardExceeded("disk_limit") from exc
        raise GuardExceeded("measurement_unavailable") from exc
    except Exception as exc:
        raise GuardExceeded("measurement_unavailable") from exc


def watch_pilot(proc_handle, config, *, cidfile, env, interval=0.5,
                margin=1024**3, clock=time.monotonic, sleep=time.sleep,
                measure=admit, stop=None, snapshot=None):
    """Identity-bound PX pilot guard, stopped only by exact CID."""
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    table = proc.snapshot() if snapshot is None else snapshot()
    bound = binding.bind_container(binding.read_cid(cidfile), env, snapshot=table)

    def take():
        return proc.snapshot() if snapshot is None else snapshot()

    def terminate(cid):
        if stop is not None:
            stop(cid)
        else:
            teardown.stop_cid(env, cid)

    return watch_bound(
        bound, limit=config["rss_bytes"], wall_seconds=config["wall_seconds"],
        running=(lambda: proc_handle.poll() is None), snapshot=take,
        measure=(lambda: _disk(config, margin, measure)), stop=terminate,
        clock=clock, sleep=sleep, interval=interval)


def watch_build(proc_handle, config, *, interval=0.5, margin=1024**3,
                clock=time.monotonic, sleep=time.sleep, measure=admit,
                stop=None, snapshot=None):
    """Launcher-tree guard for builds: no CID, exact process-group teardown."""
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    table = proc.snapshot() if snapshot is None else snapshot()
    bound = build.bind_launcher(proc_handle.pid, snapshot=table)

    def take():
        return proc.snapshot() if snapshot is None else snapshot()

    def terminate(_cid):
        if stop is not None:
            stop(bound, proc_handle)
        else:
            build.stop_group(bound, proc_handle)

    return watch_bound(
        bound, limit=config["rss_bytes"], wall_seconds=config["wall_seconds"],
        running=(lambda: proc_handle.poll() is None), snapshot=take,
        measure=(lambda: _disk(config, margin, measure)), stop=terminate,
        clock=clock, sleep=sleep, interval=interval, rss_fn=build.rss)


def watch(proc_handle, config, *, interval=1, margin=1024**3,
          clock=time.monotonic, sleep=time.sleep, measure=admit,
          rss=rss_group_bytes, cidfile=None, env=None, stop=None,
          snapshot=None, mode=None):
    """Legacy sampler for existing callers; bound path for guarded callers."""
    bound_cid = config.get("cidfile", cidfile)
    if bound_cid is not None:
        return watch_pilot(proc_handle, config, cidfile=bound_cid,
                           env=config.get("env", env), interval=interval,
                           margin=margin, clock=clock, sleep=sleep,
                           measure=measure, stop=stop, snapshot=snapshot)
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
