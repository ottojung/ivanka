"""Terminate an over-budget benchmark process tree, escalating if needed."""
import os
import signal
import time


def enforce(pid, members, command, resident, pending, audit):
    now = time.monotonic()
    prior = pending.get(pid)
    if prior is None:
        sig = signal.SIGTERM
        pending[pid] = (now, False)
    elif now - prior[0] >= 2 and not prior[1]:
        sig = signal.SIGKILL
        pending[pid] = (prior[0], True)
    else:
        return
    audit(pid, resident, command, sig.name)
    for target in sorted(members, reverse=True):
        try:
            os.kill(target, sig)
        except ProcessLookupError:
            pass
