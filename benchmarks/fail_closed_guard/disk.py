"""Fail-closed independent filesystem reserve check.

The advisory worker lock is not a disk guarantee. A bounded P1/pilot chunk
requires an independently reserved filesystem; an unreadable disk state is a
null measurement (never zero free bytes), and a shortfall is a terminal
failure. This module is deliberately injected into ``watch.watch_bound`` so
the check is part of the guard flow, not an optional caller courtesy.
"""
import shutil

from .errors import GuardExceeded


def check_reserve(path, reserve_bytes, *, usage=None):
    """Return free bytes, or fail closed on unreadable state / short reserve."""
    if not isinstance(reserve_bytes, (int, float)) or reserve_bytes <= 0:
        raise GuardExceeded("invalid_config")
    try:
        free = (usage or shutil.disk_usage)(str(path)).free
    except Exception as exc:
        raise GuardExceeded("measurement_unavailable") from exc
    if free is None or not isinstance(free, (int, float)):
        raise GuardExceeded("measurement_unavailable")
    if free < reserve_bytes:
        raise GuardExceeded("reserve_shortfall")
    return int(free)
