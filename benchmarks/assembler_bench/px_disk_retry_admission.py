"""Extra, evidence-based workspace headroom before a PX ``disk_stop`` retry.

An arm that stopped on disk must not spend its finite retry allowance merely
because a launcher released its own temporary files: the retry needs strictly
more verified free space than an ordinary arm reservation. A refusal is
recorded as durable deferred state and leaves the original terminal receipt,
its index entry, the checkpoint and the retry authorization untouched.

This module only reads admission evidence and writes a deferred-state record.
It never launches a process or edits a PX receipt, index, checkpoint or
registry, and it never weakens the 32 GiB shared-workspace reserve.
"""
import json
from pathlib import Path

from . import px_cohort_scheduler as sched

SCHEMA = "ivanka.px.disk-retry-deferred.v1"
ADMISSION_SCHEMA = "ivanka.px.disk-retry-admission.v1"
DEFAULT_EXTRA_BYTES = 1024**3
_IDENTITY = ("tool_id", "cohort", "alias", "input_sha256", "source_commit",
             "adapter_commit", "image_sha256")


def proposed_reservation(reserve_bytes, extra_bytes=DEFAULT_EXTRA_BYTES):
    """Return a strictly larger reservation still inside the reviewed 1-4 GiB bound."""
    if (isinstance(reserve_bytes, bool) or not isinstance(reserve_bytes, int)
            or not sched.MIN_RESERVE <= reserve_bytes <= sched.MAX_RESERVE):
        raise ValueError("PX base reservation must be 1-4 GiB")
    if (isinstance(extra_bytes, bool) or not isinstance(extra_bytes, int)
            or extra_bytes < 1):
        raise ValueError("disk_stop retry needs a positive extra headroom")
    proposed = reserve_bytes + extra_bytes
    if proposed <= reserve_bytes or proposed > sched.MAX_RESERVE:
        raise ValueError("disk_stop retry reservation exceeds reviewed bound")
    return proposed


def deferred_path(root, arm):
    """Durable, arm-scoped record; never reuses a case receipt path."""
    return (Path(root) / "deferred" / (sched.receipt_id(arm) + ".json"))


def evaluate(registry, baseline, root, reserve_bytes, *,
             extra_bytes=DEFAULT_EXTRA_BYTES, available=None):
    """Admit a disk_stop retry only with strictly more verified free space.

    Any admission failure — including a registry or baseline that no longer
    verifies — defers the retry instead of consuming another attempt. The
    decision carries the measured evidence so an operator can tell a genuine
    headroom shortage from a broken admission input.
    """
    proposed = proposed_reservation(reserve_bytes, extra_bytes)
    if not isinstance(baseline, dict):
        baseline = json.loads(Path(baseline).read_text())
    decision = {
        "schema": ADMISSION_SCHEMA,
        "action": "defer",
        "base_reservation_bytes": reserve_bytes,
        "extra_headroom_bytes": proposed - reserve_bytes,
        "proposed_reservation_bytes": proposed,
        "reason": "extra_headroom_unverified",
    }
    if available is not None:
        free = available(baseline["workspace"])
        if isinstance(free, bool) or not isinstance(free, int) or free < 0:
            raise ValueError("invalid workspace free-space measurement")
        decision["free_bytes"] = free
    try:
        admitted = sched.admit_arm(registry, baseline, root, proposed)
    except ValueError as exc:
        # Fail closed: no extra verified headroom means no second attempt.
        decision["reason"] = str(exc)
    else:
        decision.update(action="retry", reason="verified_extra_headroom",
                        free_bytes=admitted["free_bytes"],
                        admitted_reservation_bytes=proposed)
    return decision


def record_deferred(root, arm, decision, *, prior):
    """Persist an immutable deferral receipt for one armed disk_stop failure."""
    if not isinstance(decision, dict) or decision.get("action") != "defer":
        raise ValueError("only a deferred decision is recordable")
    if (not isinstance(prior, dict) or prior.get("outcome") != "failure"
            or prior.get("failure_reason") != "disk_stop"):
        raise ValueError("only a disk_stop failure can be deferred")
    payload = {"schema": SCHEMA,
               **{key: arm[key] for key in _IDENTITY},
               "attempt": prior["attempt"], "failure_reason": "disk_stop",
               "decision": decision}
    blob = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = deferred_path(root, arm)
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError("deferred PX state changed for this arm")
        return path
    sched._atomic_write(path, blob)
    return path
