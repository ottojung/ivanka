"""Stop only an exact known CID and prove it is gone. No bare PID signals."""
import subprocess

from .binding import CID, command
from .errors import TeardownError


def _listed(env):
    return set(command(["podman", "ps", "-a", "--no-trunc",
                        "--format", "{{.ID}}"], env).splitlines())


def stop_cid(env, cid, timeout=45):
    """Idempotent exact-CID removal with before/after proof."""
    if not CID.fullmatch(cid):
        raise TeardownError("invalid_cid")
    was_present = cid in _listed(env)
    if was_present:
        subprocess.run(["podman", "rm", "-f", cid], env=env, check=True,
                       capture_output=True, text=True, timeout=timeout)
    if cid in _listed(env):
        raise TeardownError("container_survived")
    return {"cid": cid, "container_removed": was_present,
            "kernel_enforcement": False}


def _inspected(env, cid):
    """True only when inspection in the pinned store names this exact CID."""
    try:
        fields = command(["podman", "inspect", "--format",
                          "{{.Id}} {{.State.Pid}}", cid], env).split()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").lower()
        if "no such object" in detail or "no such container" in detail:
            return False
        raise TeardownError("verification_unavailable") from exc
    except (OSError, ValueError) as exc:
        raise TeardownError("verification_unavailable") from exc
    return len(fields) == 2 and fields[0] == cid


def stop_verified_cid(env, cid, timeout=45):
    """Remove a CID obtained from a durable lease, proving absence by inspect.

    Listing is never used to discover or choose the target. A CID that cannot
    be proven absent stays a failed teardown rather than a claimed success.
    """
    if not CID.fullmatch(cid):
        raise TeardownError("invalid_cid")
    present = _inspected(env, cid)
    if present:
        subprocess.run(["podman", "rm", "-f", cid], env=env, check=True,
                       capture_output=True, text=True, timeout=timeout)
    if _inspected(env, cid):
        raise TeardownError("container_survived")
    return {"cid": cid, "container_removed": present,
            "method": "exact_cid_inspect", "kernel_enforcement": False}
