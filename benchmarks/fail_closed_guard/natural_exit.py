"""Exact-CID natural-exit attestation for the shared fail-closed guard.

A launcher ending is not evidence that its container finished: a launcher
poll can lag container exit, and a missing ``/proc`` record can be a sampling
race or a live identity loss. This module accepts a natural exit only when the
exact bound CID is proven absent by inspection *and* the launcher supplies a
real integer result. Teardown proof is verified separately by :mod:`watch`
before any success receipt is returned.
"""
from . import binding
from .errors import GuardExceeded


def attest(cid, env, returncode, *, inspect=None):
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
    if look(cid) is not None:
        raise GuardExceeded("identity_lost")
    if look(cid) is not None:
        raise GuardExceeded("natural_exit_unverified")
    return {"cid": cid, "returncode": returncode,
            "method": "exact_cid_inspect",
            "absence_proof": {"observed_absent": True,
                              "inspected_absent_twice": True},
            "kernel_enforcement": False}
