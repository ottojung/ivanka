"""Stop only an exact known CID and prove it is gone. No bare PID signals."""
import subprocess
import time

from .binding import CID, absent_evidence, command
from .errors import GuardExceeded, TeardownError


def _listed(env):
    return set(command(["podman", "ps", "-a", "--no-trunc",
                        "--format", "{{.ID}}"], env).splitlines())


# Only an inspect-based teardown may prove absence when the container was
# already removed by another owner (e.g. the watchdog raced the controller).
# A bare "not present" observation is never enough to retire a lease.
AUTHORITATIVE_ABSENCE_METHODS = ("exact_cid_inspect",)


def valid_proof(proof, cid):
    """True only for an exact-CID proof carrying a fresh absence check.

    ``container_removed`` describes who removed the container, not whether it
    is gone. When a watchdog removed it first, the controller's idempotent
    stop sees it absent and reports ``False``; an authoritative inspect proof
    still establishes the fresh absence that makes STOP retirement safe.
    """
    if not isinstance(proof, dict) or proof.get("cid") != cid:
        return False
    if proof.get("fresh_absence_check") is not True:
        return False
    if proof.get("container_removed") is True:
        return True
    return (proof.get("method") in AUTHORITATIVE_ABSENCE_METHODS
            and isinstance(proof.get("absence_proof"), dict)
            and proof["absence_proof"].get("observed_absent") is True)


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


def _inspected(env, cid):
    """True only when the pinned store inspects this exact CID to a live PID.

    False means *proven* absence: podman named this exact CID as not existing.
    A wrong field count, a mismatched CID, a non-numeric PID or an unrelated
    tool error is a broken observation and must raise, never be read as an
    absent container that would let a lease retire on a false proof.
    """
    try:
        fields = command(["podman", "inspect", "--format",
                          "{{.Id}} {{.State.Pid}}", cid], env).split()
    except subprocess.CalledProcessError as exc:
        if absent_evidence(exc, cid):
            return False
        raise TeardownError("verification_unavailable") from exc
    except (OSError, ValueError) as exc:
        raise TeardownError("verification_unavailable") from exc
    if len(fields) != 2 or fields[0] != cid or not fields[1].isdigit():
        raise TeardownError("verification_unavailable")
    return True


def stop_verified_cid(env, cid, timeout=45):
    """Remove a CID obtained from a durable lease, proving absence by inspect.

    Listing is never used to discover or choose the target. A CID that cannot
    be proven absent stays a failed teardown rather than a claimed success.
    The returned proof is authoritative even when the container was already
    absent before this call (a watchdog/controller teardown race).
    """
    if not CID.fullmatch(cid):
        raise TeardownError("invalid_cid")
    present = _inspected(env, cid)
    if present:
        subprocess.run(["podman", "rm", "-f", cid], env=env, check=True,
                       capture_output=True, text=True, timeout=timeout)
    after = _inspected(env, cid)
    if after:
        raise TeardownError("container_survived")
    return {"cid": cid, "container_removed": present,
            "fresh_absence_check": True, "method": "exact_cid_inspect",
            "absence_proof": {"observed_absent": True,
                              "inspected_before": present,
                              "inspected_after": after,
                              "checked_at_utc": time.strftime(
                                  "%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            "kernel_enforcement": False}


def require_proof(proof, cid):
    """Fail closed with an evidence-bearing GuardExceeded on a bad proof."""
    if valid_proof(proof, cid):
        return proof
    raise GuardExceeded("teardown_unverified", teardown=proof,
                        teardown_error="invalid_or_missing_fresh_absence_proof")
