"""Track and stop ONLY a PX pilot container created by the locked launcher."""
import re
import subprocess
from pathlib import Path

from .cleanup import ROOT, STORE, command

CID = re.compile(r"[0-9a-f]{64}\Z")
RAM_LIMIT = 4_000_000_000  # Fixed PX acceptance policy, not an env override.
FORBIDDEN = ("-m", "--memory", "--memory-swap", "--net", "--network",
             "--cgroups", "--cgroupns", "--privileged")


def bind_pilot(root, mode, argv, ident):
    """Inject a per-attempt CID file; no arbitrary shell escapes on live PX."""
    if mode != "pilot" or Path(root).resolve() != ROOT:
        return list(argv), None
    if (list(argv[:2]) != ["podman", "run"]
            or any(str(arg).startswith("--cidfile") for arg in argv)
            or any(str(arg) == flag or str(arg).startswith(flag + "=")
                   for arg in argv[2:] for flag in FORBIDDEN)):
        raise ValueError("PX pilots require guarded foreground podman options")
    cidfile = Path(root) / ("pilot-" + ident + ".cid")
    if cidfile.exists() or cidfile.is_symlink():
        raise ValueError("pilot container identifier already exists")
    # --rm deletes the CID file before verification on natural completion.
    # Keep the container ID until the exact-CID cleanup below runs.
    tail = [arg for arg in argv[2:] if arg != "--rm"]
    return [*argv[:2], "--cidfile", str(cidfile),
            f"--memory={RAM_LIMIT}", "--network=none", *tail], cidfile


def stop_pilot(root, env, cidfile):
    """Reap the exact issued CID, never scan/kill unrelated containers."""
    if (Path(root).resolve() != ROOT or cidfile.parent != ROOT
            or env.get("CONTAINERS_STORAGE_CONF") != str(ROOT / "storage.conf")):
        raise ValueError("wrong PX container cleanup provenance")
    if command(["podman", "info", "--format", "{{.Store.GraphRoot}}"], env) != STORE:
        raise ValueError("wrong PX graphroot")
    if not cidfile.is_file() or cidfile.is_symlink():
        raise RuntimeError("missing or unsafe PX pilot CID file")
    cid = cidfile.read_text().strip()
    if not CID.fullmatch(cid):
        raise RuntimeError("invalid PX pilot CID")
    before = command(["podman", "ps", "-a", "--no-trunc",
                      "--format", "{{.ID}}"], env).splitlines()
    if cid in before:
        subprocess.run(["podman", "rm", "-f", cid], env=env, check=True,
                       capture_output=True, text=True, timeout=45)
    after = command(["podman", "ps", "-a", "--no-trunc",
                     "--format", "{{.ID}}"], env).splitlines()
    if cid in after:
        raise RuntimeError("pilot container survived guarded cleanup")
    return {"pilot_container_id": cid, "container_removed": cid in before}
