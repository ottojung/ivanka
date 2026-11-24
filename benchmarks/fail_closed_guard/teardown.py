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
