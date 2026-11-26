"""Prospective P1 watchdog helper. NOT wired into the live controller.

Thin adapter over the shared fail_closed_guard: exact-CID binding, bound whole
container-tree RSS, fail-closed disk reserve, and CID-only teardown proof. No
hard-cap claim is made; ``kernel_enforcement`` is always false.
"""
import time

from . import binding, disk, natural_exit, proc, teardown, watch
from .errors import GuardExceeded


def bind(name, env):
    """Resolve the exact CID behind a known P1 container name."""
    return binding.bind_by_name(name, env)


def bind_cid(cid, env):
    """Bind an already-issued exact CID without a name lookup."""
    return binding.bind_container(cid, env)


def observe(bound, snapshot=None):
    table = snapshot if snapshot is not None else proc.snapshot()
    from . import identity, startup, tree
    if bound.get("stable"):
        pid = startup.locate(bound, table)
    else:
        pid = identity.locate(bound["fingerprint"], table)
    group = tree.members(table, pid, bound["fingerprint"])
    return tree.rss_bytes(table, group)


def check_reserve(path, reserve_bytes, *, usage=None):
    """Independently fail closed on disk reserve shortfall / unreadable disk."""
    return disk.check_reserve(path, reserve_bytes, usage=usage)


def watch_p1(bound, *, limit, wall_seconds, running, measure, env,
             clock=None, sleep=None, snapshot=None, disk_path=None,
             disk_reserve_bytes=None, disk_usage=None, strict_proof=True,
             attestation=None, audit=None, start=None, launcher=None,
             interval=0.5):
    """Same fail-closed watcher; CID-only teardown with exact-CID proof.

    Supplying ``launcher`` (an object with ``poll()`` or a poll callable) makes
    exact-CID natural-exit attestation mandatory: a missing /proc PID can no
    longer end the arm on a lagging launcher poll. The bound CID, pinned
    ``env`` and the watcher's monotonic start + wall budget are shared with the
    attestation; omitting ``launcher`` retains the legacy caller contract.
    """
    kwargs = {}
    for key, value in (("clock", clock), ("sleep", sleep), ("audit", audit),
                       ("attestation", attestation)):
        if value is not None:
            kwargs[key] = value
    poll = launcher.poll if callable(getattr(launcher, "poll", None)) else launcher
    if launcher is not None and not callable(poll):
        raise GuardExceeded("natural_exit_unverified")
    if launcher is not None:
        tick = clock if clock is not None else time.monotonic
        if start is None:
            start = tick()
        kwargs["start"] = start
        kwargs["attest_exit"] = (
            lambda: natural_exit.wait_and_attest(
                bound["cid"], env, poll, start=start,
                wall_seconds=wall_seconds, interval=interval,
                clock=tick, sleep=(sleep if sleep is not None else time.sleep)))
    elif start is not None:
        kwargs["start"] = start
    return watch.watch_bound(
        bound, limit=limit, wall_seconds=wall_seconds, running=running,
        snapshot=(lambda: (snapshot() if callable(snapshot)
                           else (snapshot if snapshot is not None
                                 else proc.snapshot()))),
        measure=measure, stop=(lambda cid: teardown.stop_cid(env, cid)),
        disk_path=disk_path, disk_reserve_bytes=disk_reserve_bytes,
        disk_usage=disk_usage, strict_proof=strict_proof, interval=interval,
        **kwargs)


__all__ = ["bind", "bind_cid", "observe", "check_reserve", "watch_p1",
           "GuardExceeded"]
