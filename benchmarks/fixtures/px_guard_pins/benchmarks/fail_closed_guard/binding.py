"""Verified container CID/init binding (read-only inspect, never a signal)."""
import re
import subprocess
from pathlib import Path

from . import proc, startup
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


def absent_evidence(exc, cid):
    """True only when podman proves this exact CID is absent.

    A generic "no such object" for a different name is a tool/observer fault,
    not proof that our CID is gone. Only an error naming the exact CID may be
    treated as absence; everything else stays a verification failure.
    """
    detail = getattr(exc, "stderr", "") or ""
    if isinstance(detail, bytes):
        detail = detail.decode("utf-8", "replace")
    # CalledProcessError.__str__ includes the requested CID in its argv,
    # even when stderr names an unrelated object. Only an unambiguous
    # diagnostic naming the exact CID is evidence, not the invocation.
    if not CID.fullmatch(cid) or not isinstance(detail, str):
        return False
    return re.fullmatch(
        r"""(?:Error:\s*)?no such (?:object|container):?\s+(?P<quote>["']?)"""
        + re.escape(cid) + r"(?P=quote)", detail.strip(),
        flags=re.IGNORECASE) is not None


def inspect_pid(cid, env):
    out = command(["podman", "inspect", "--format",
                   "{{.Id}} {{.State.Pid}}", cid], env)
    fields = out.split()
    if len(fields) != 2 or fields[0] != cid or not fields[1].isdigit():
        raise GuardExceeded("identity_lost")
    return int(fields[1])


def inspect_pid_if_live(cid, env):
    """Return the live init PID, or None for a proven exited/absent CID.

    A naturally finished container reports PID 0 (still present) or a podman
    error naming this exact CID (already removed). Both are honest absence,
    never a measurement or identity failure. Malformed or mismatched inspect
    output is ``identity_lost`` and an unusable tool is
    ``inspection_unavailable``; neither may be downgraded to "absent".
    """
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    try:
        fields = command(["podman", "inspect", "--format",
                          "{{.Id}} {{.State.Pid}}", cid], env).split()
    except subprocess.CalledProcessError as exc:
        if absent_evidence(exc, cid):
            return None
        raise GuardExceeded("inspection_unavailable") from exc
    except (OSError, ValueError) as exc:
        raise GuardExceeded("inspection_unavailable") from exc
    if len(fields) != 2 or fields[0] != cid or not fields[1].isdigit():
        raise GuardExceeded("identity_lost")
    return int(fields[1]) or None


def bind_container(cid, env, snapshot=None):
    """Bind the exact CID to the live init process and immutable identity.

    Inspect the exact CID *before* sampling: the sample must describe the
    process that inspection attests, not one observed earlier. A second
    read-only inspection then proves the same CID still resolves to the same
    init PID; a change is terminal ``identity_lost``. ``snapshot`` may be a
    table (legacy callers) or a zero-argument sampler (the startup watcher),
    which is invoked strictly after the first inspection. No PID is signalled
    and no volatile cmdline hash is used as identity.
    """
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    pid = inspect_pid(cid, env)
    table = snapshot() if callable(snapshot) else snapshot
    if table is None:
        table = proc.snapshot()
    if inspect_pid(cid, env) != pid:
        raise GuardExceeded("identity_lost")
    return bind_sampled(cid, pid, table)


def bind_sampled(cid, pid, table):
    """Bind from a snapshot taken strictly after inspecting the exact CID.

    The caller inspects ``cid -> pid`` before and after the sample and expects
    the same answer both times; ``inspect_pid`` itself proves ``{{.Id}} == cid``
    on every call. This helper only binds that already-captured record: it
    never re-samples, never signals a PID and never turns a missing observation
    into a success.
    """
    if not CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    record = table.get(pid)
    if record is None:
        raise GuardExceeded("identity_lost")
    return startup.bind(cid, pid, record, cid_verified=True)


def bind_by_name(name, env, snapshot=None):
    """Resolve an exact CID from a known container name, then bind it."""
    cid = command(["podman", "inspect", "--format", "{{.Id}}", name], env)
    return bind_container(cid, env, snapshot=snapshot)
