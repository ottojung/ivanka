"""Stop only an exact known CID and prove it is gone. No bare PID signals."""
import subprocess
import time

from .binding import CID, command
from .errors import GuardExceeded, TeardownError


def _listed(env):
    return set(command(["podman", "ps", "-a", "--no-trunc",
                        "--format", "{{.ID}}"], env).splitlines())


def valid_proof(proof, cid):
    """True only for an exact-CID proof carrying a fresh absence check."""
    return (isinstance(proof, dict) and proof.get("cid") == cid
            and proof.get("container_removed") is True
            and proof.get("fresh_absence_check") is True)


def stop_cid(env, cid, timeout=45):
    """Idempotent exact-CID removal with before/after fresh-absence proof."""
    if not CID.fullmatch(cid):
        raise TeardownError("invalid_cid")
    before = _listed(env)
    was_present = cid in before
    if was_present:
        subprocess.run(["podman", "rm", "-f", cid], env=env, check=True,
                       capture_output=True, text=True, timeout=timeout)
    after = _listed(env)
    if cid in after:
        raise TeardownError("container_survived")
    return {"cid": cid, "container_removed": was_present,
            "fresh_absence_check": True,
            "absence_proof": {"listed_before": sorted(before),
                              "listed_after": sorted(after),
                              "checked_at_utc": time.strftime(
                                  "%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            "kernel_enforcement": False}


def require_proof(proof, cid):
    """Fail closed with an evidence-bearing GuardExceeded on a bad proof."""
    if valid_proof(proof, cid):
        return proof
    raise GuardExceeded("teardown_unverified", teardown=proof,
                        teardown_error="invalid_or_missing_fresh_absence_proof")
