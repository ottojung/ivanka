"""Prospective P1 harness integration on the shared fail_closed_guard.

SOURCE-ONLY: this adapter never starts a container, places a STOP sentinel,
takes the PX shared lock, edits a receipt, or touches frozen MiCall / images /
sealed evidence. The caller supplies the bounded operation (``running`` and
``measure``); the adapter only gates it.

Evidence honesty: earlier P1 peaks (~38 MB) sampled the Podman launcher
process group and were mislabelled ``whole_container_process_tree``. They are
RETAINED as diagnostic only with ``memory_scope=unverified``; no hard-cap claim
is made here. Every result carries ``kernel_enforcement=False`` and
``enforcement=userspace_observed``.
"""
import time

from . import binding, lease, proc, stop, teardown, watch
from .errors import GuardExceeded

DEFAULT_RESERVE_BYTES = 32 * 1024 ** 3  # independent project filesystem reserve

P1_ATTESTATION = {
    "rss_sample_scope": "whole_container_process_tree",
    "method": "exact_cid_to_init_pid_starttime_pidns_bound_tree_sampled_rss",
    "version": "ivanka.p1.shared-guard.v1",
    "kernel_enforcement": False,
}


def bind_p1(name_or_cid, env, *, snapshot=None):
    """Bind by exact 64-hex CID, or by container name when not CID-shaped."""
    if isinstance(name_or_cid, str) and binding.CID.fullmatch(name_or_cid):
        return binding.bind_container(name_or_cid, env, snapshot=snapshot)
    return binding.bind_by_name(name_or_cid, env, snapshot=snapshot)


def run_guarded(bound, *, owner, lease_root, stop_path, limit, wall_seconds,
                running, measure, env, disk_path,
                disk_reserve_bytes=DEFAULT_RESERVE_BYTES, disk_usage=None,
                snapshot=None, clock=None, sleep=None, audit=None,
                attestation=None, start=None):
    """Run a caller-supplied bounded operation under the shared guard.

    Ordering is fail-closed:

    1. reconcile the durable lease journal; refuse admission while any prior
       owned container/process is still alive or its state is unknown;
    2. acquire and CID-bind the lease under the real owner BEFORE sampling;
    3. require the operator STOP sentinel to be armed (never launch without
       it), and re-check the independent disk reserve every sample;
    4. watch the bound whole-container tree; every exit proves exact-CID
       teardown by ``teardown.stop_cid`` with a fresh absence check;
    5. ONLY the active lease owner may retire STOP, and only with that proof;
       retirement also closes the lease in the append-only journal.

    Any failure with no valid teardown proof leaves STOP armed and the lease
    OPEN, so a later controller still fails closed at admission.
    """
    cid = bound.get("cid") if isinstance(bound, dict) else None
    if not isinstance(cid, str) or not binding.CID.fullmatch(cid):
        raise GuardExceeded("invalid_lease")
    if not owner:
        raise GuardExceeded("invalid_lease")

    lease.require_clear(lease_root, env)
    ident = "p1-%s-%s-%d" % (str(owner), cid[:12], int(time.time()))
    lease.acquire(lease_root, ident, "pilot", owner=owner, cid=cid)
    lease.bind_cid(lease_root, ident, cid, owner=owner,
                   pid=bound.get("pid"), fingerprint=bound.get("fingerprint"))

    if not stop.is_armed(stop_path):
        raise GuardExceeded("stop_absent")

    supplied = dict(P1_ATTESTATION)
    if attestation:
        supplied.update(attestation)

    kwargs = {}
    for key, value in (("clock", clock), ("sleep", sleep), ("audit", audit),
                       ("start", start)):
        if value is not None:
            kwargs[key] = value

    proof = None
    outcome = None
    try:
        result = watch.watch_bound(
            bound, limit=limit, wall_seconds=wall_seconds, running=running,
            snapshot=(lambda: proc.snapshot() if snapshot is None else snapshot()),
            measure=measure, stop=(lambda c: teardown.stop_cid(env, c)),
            disk_path=disk_path, disk_reserve_bytes=disk_reserve_bytes,
            disk_usage=disk_usage, strict_proof=True, attestation=supplied,
            **kwargs)
        proof = result.get("teardown")
        outcome = {"status": "completed", "result": result}
    except GuardExceeded as exc:
        proof = exc.teardown
        outcome = {"status": "fail_closed", "reason": exc.reason,
                   "result": exc.guard_result,
                   "teardown_error": exc.teardown_error}
    except Exception as exc:
        raise GuardExceeded("measurement_unavailable",
                            teardown_error=str(exc)[:320]) from exc

    # Owner authorization is enforced here: a foreign caller cannot retire
    # STOP or close this lease, even with a fabricated proof.
    stop.retire_stop(stop_path, proof, owner=owner, lease_root=lease_root,
                     cid=cid)
    outcome["stop_retired_by"] = str(owner)
    if outcome["status"] == "fail_closed":
        raise GuardExceeded(outcome["reason"], guard_result=outcome["result"],
                            teardown=proof,
                            teardown_error=outcome.get("teardown_error"))
    return outcome


__all__ = ["bind_p1", "run_guarded", "DEFAULT_RESERVE_BYTES",
           "P1_ATTESTATION", "GuardExceeded"]
