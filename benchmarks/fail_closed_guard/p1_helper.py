"""Prospective P1 watchdog helper. NOT wired into the live controller."""
from . import binding, proc, teardown, watch


def bind(name, env):
    """Resolve the exact CID behind a known P1 container name."""
    return binding.bind_by_name(name, env)


def observe(bound, snapshot=None):
    table = snapshot if snapshot is not None else proc.snapshot()
    from . import identity, startup, tree
    if bound.get("stable"):
        # Exact-CID binding uses immutable kernel identity; a normal exec must
        # not be mistaken for PID reuse here either.
        pid = startup.locate(bound, table)
    else:
        pid = identity.locate(bound["fingerprint"], table)
    group = tree.members(table, pid, bound["fingerprint"])
    return tree.rss_bytes(table, group)


def watch_p1(bound, *, limit, wall_seconds, running, measure, env,
             clock=None, sleep=None, snapshot=None):
    """Same fail-closed watcher; CID-only teardown with teardown proof."""
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    if sleep is not None:
        kwargs["sleep"] = sleep
    return watch.watch_bound(
        bound, limit=limit, wall_seconds=wall_seconds, running=running,
        snapshot=(lambda: proc.snapshot() if snapshot is None else snapshot),
        measure=measure, stop=(lambda cid: teardown.stop_cid(env, cid)), **kwargs)
