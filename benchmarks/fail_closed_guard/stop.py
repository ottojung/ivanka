"""Owner-authorized STOP sentinel retirement.

A STOP sentinel is a coordination signal shared with other workers. Removing
it is only safe after the owning worker has proven exact-CID teardown, and
only the owner named on the still-open lease may do it. A foreign owner, a
foreign CID, an absent proof or an anonymous "just unlink it" call all fail
closed with the sentinel left in place.
"""
import time
from pathlib import Path

from . import lease, teardown
from .errors import GuardExceeded

HOLD_TOKENS = ("", "hold", "hold\n")


def arm(path, owner):
    """Create an owner-bound STOP sentinel (idempotent while already armed)."""
    import os
    target = Path(path)
    if target.is_symlink():
        raise GuardExceeded("stop_unavailable")
    if target.exists():
        return str(target)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return str(target)
    with os.fdopen(fd, "w") as stream:
        stream.write(str(owner) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return str(target)


def is_armed(path):
    target = Path(path)
    return target.is_file() and not target.is_symlink()


def retire_stop(path, proof, *, owner, lease_root, cid=None):
    """Retire STOP only for the active lease owner after a valid proof.

    Returns an append-only audit record. The caller must already have proven
    teardown through ``teardown.stop_cid`` (validated here again), so a
    controller that died mid-run leaves its lease OPEN and its STOP in place:
    admission keeps failing closed until the real owner cleans up.
    """
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise GuardExceeded("stop_absent")
    proof_cid = proof.get("cid") if isinstance(proof, dict) else None
    bound_cid = cid if cid is not None else proof_cid
    teardown.require_proof(proof, bound_cid)

    token = target.read_text().strip()
    if token not in HOLD_TOKENS and token != str(owner):
        raise GuardExceeded("stop_owner_unauthorized")

    try:
        active = {key: event for key, event in
                  lease.latest(lease.events(lease_root)).items()
                  if event.get("state") not in lease.CLOSED}
    except (OSError, ValueError, TypeError, GuardExceeded) as exc:
        raise GuardExceeded("journal_unreadable") from exc
    candidates = [event for event in active.values()
                  if lease._owner_of(event) == str(owner)
                  and (bound_cid is None or event.get("cid") in (None, bound_cid))]
    if not candidates:
        raise GuardExceeded("stop_owner_unauthorized")
    if len(candidates) != 1:
        raise GuardExceeded("stop_owner_ambiguous")
    owned = candidates[0]

    audit = {"schema": lease.SCHEMA, "event": "stop_retired",
             "lease": owned["lease"], "owner": str(owner), "cid": bound_cid,
             "proof": proof, "at_utc": time.time()}
    lease.append(lease_root, audit)
    target.unlink()
    lease.release(lease_root, owned["lease"], owner=owner, cid=bound_cid,
                  proof=proof)
    return audit
