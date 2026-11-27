"""Exact-CID natural-exit attestation for the shared fail-closed guard.

A launcher ending is not evidence that its container finished: a launcher
poll can lag container exit, and a missing ``/proc`` record can be a sampling
race or a live identity loss. This module accepts a natural exit only when the
exact bound CID is proven absent by inspection *and* the launcher supplies a
real integer result. Teardown proof is verified separately by :mod:`watch`
before any success receipt is returned.
"""
import time

from . import binding
from .errors import GuardExceeded

# A launcher poll may lag container exit. Bound the number of confirmations so
# a stalled launcher cannot hold a guard loop open indefinitely.
CONFIRMATIONS = 32


def wait_and_attest(cid, env, poll, *, start, wall_seconds, interval=0.5,
                    clock=time.monotonic, sleep=time.sleep,
                    confirmations=CONFIRMATIONS, deadline_utc=None):
    """Wait for exact-CID absence plus a real launcher result, then attest.

    The deadline is monotonic and starts with the watcher's own ``start``, so
    attestation cannot grant a fresh budget to an arm that already spent one.
    An optional absolute epoch deadline covers a restarted controller as well.
    The CID is always the exact bound CID and ``env`` is the caller's pinned
    inspection environment; neither is discovered from a launcher or a name.
    """
    if not callable(poll):
        raise GuardExceeded("natural_exit_unverified")
    deadline = start + wall_seconds

    def check():
        # Deadlines are checked before every blocking probe and again after
        # it. A real launcher result obtained past the budget is never a
        # natural completion: the arm must fail closed with exact teardown.
        if clock() >= deadline:
            raise GuardExceeded("wall_limit")
        if deadline_utc is not None and time.time() >= deadline_utc:
            raise GuardExceeded("wall_limit")

    for _ in range(confirmations):
        check()
        if binding.inspect_pid_if_live(cid, env) is not None:
            raise GuardExceeded("identity_lost")
        check()  # inspection is a blocking probe and may cross the deadline
        result = poll()
        check()  # poll is a probe; never act on a result obtained past deadline
        if result is not None:
            return attest(cid, env, result, deadline_check=check)
        sleep(interval)
        check()
    raise GuardExceeded("natural_exit_unverified")


def attest(cid, env, returncode, *, inspect=None, deadline_check=None):
    """Prove a natural exit from exact-CID absence and a real launcher result.

    ``returncode`` must be an integer returned by ``poll()``; ``None`` is an
    unfinished launcher and never attests an exit. Inspection must prove the
    exact CID absent twice (a reported init PID of zero, or a diagnostic
    naming exactly this CID). A live init PID means the bound container
    survived its launcher, which is a live identity loss; an unusable or
    ambiguous inspection is never absence. No PID is signalled here.
    """
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise GuardExceeded("natural_exit_unverified")
    if not binding.CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    look = inspect if inspect is not None else (
        lambda value: binding.inspect_pid_if_live(value, env))
    # Both authoritative absence inspections are blocking probes. A caller
    # that owns a wall/absolute deadline supplies the check so neither proof
    # can be collected after the budget expired.
    if deadline_check is not None:
        deadline_check()
    if look(cid) is not None:
        raise GuardExceeded("identity_lost")
    if deadline_check is not None:
        deadline_check()
    if look(cid) is not None:
        raise GuardExceeded("natural_exit_unverified")
    if deadline_check is not None:
        deadline_check()
    return {"cid": cid, "returncode": returncode,
            "method": "exact_cid_inspect",
            "absence_proof": {"observed_absent": True,
                              "inspected_absent_twice": True},
            "kernel_enforcement": False}
