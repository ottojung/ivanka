"""Prospective P1 watchdog helper. NOT wired into the live controller.

Thin adapter over the shared fail_closed_guard: exact-CID binding, bound whole
container-tree RSS, fail-closed disk reserve, and CID-only teardown proof. No
hard-cap claim is made; ``kernel_enforcement`` is always false.
"""
from . import binding, disk, proc, teardown, watch
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
             attestation=None, audit=None, start=None):
    """Same fail-closed watcher; CID-only teardown with exact-CID proof."""
    kwargs = {}
    for key, value in (("clock", clock), ("sleep", sleep), ("audit", audit),
                       ("attestation", attestation), ("start", start)):
        if value is not None:
            kwargs[key] = value
    return watch.watch_bound(
        bound, limit=limit, wall_seconds=wall_seconds, running=running,
        snapshot=(lambda: proc.snapshot() if snapshot is None else snapshot),
        measure=measure, stop=(lambda cid: teardown.stop_cid(env, cid)),
        disk_path=disk_path, disk_reserve_bytes=disk_reserve_bytes,
        disk_usage=disk_usage, strict_proof=strict_proof, **kwargs)


__all__ = ["bind", "bind_cid", "observe", "check_reserve", "watch_p1",
           "GuardExceeded"]
