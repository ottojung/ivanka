"""Verified container CID/init binding (read-only inspect, never a signal)."""
import re
import subprocess
from pathlib import Path

from . import identity, proc
from .errors import GuardExceeded

CID = re.compile(r"[0-9a-f]{64}\Z")


def command(argv, env, timeout=15):
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def read_cid(cidfile):
    path = Path(cidfile)
    if path.is_symlink() or not path.is_file():
        raise GuardExceeded("binding_unavailable")
    cid = path.read_text().strip()
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    return cid


def cidfile_absent(cidfile):
    """Distinguish a transiently absent issued CID file from a bad one.

    Podman creates --cidfile asynchronously. Only genuine absence of a safe
    path may be retried during startup; a symlink, a directory or any other
    error is a provenance fault and must fail closed without a wait.
    """
    path = Path(cidfile)
    if path.is_symlink():
        return False
    try:
        path.stat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def inspect_pid(cid, env):
    out = command(["podman", "inspect", "--format",
                   "{{.Id}} {{.State.Pid}}", cid], env)
    fields = out.split()
    if len(fields) != 2 or fields[0] != cid:
        raise GuardExceeded("identity_lost")
    return int(fields[1])


def bind_container(cid, env, snapshot=None):
    """Bind exact CID to the live init process and immutable identity."""
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    pid = inspect_pid(cid, env)
    table = snapshot if snapshot is not None else proc.snapshot()
    record = table.get(pid)
    if record is None:
        raise GuardExceeded("identity_lost")
    return {"cid": cid, "pid": pid,
            "fingerprint": identity.bind(record)}


def bind_by_name(name, env, snapshot=None):
    """Resolve an exact CID from a known container name, then bind it."""
    cid = command(["podman", "inspect", "--format", "{{.Id}}", name], env)
    return bind_container(cid, env, snapshot=snapshot)
