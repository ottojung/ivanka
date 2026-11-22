"""Recover only orphaned Buildah working containers in the isolated PX store.

After the monitored build group has stopped, old --external/Storage overlays
can outlive podman build and exceed the eight-GiB exploratory disk limit.
Never touch containers in another store or a running container.
"""
import os
import re
import subprocess
from pathlib import Path

STORE = "/workspace/ivanka-exploratory-podman-20261121/store"
ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
NAME = re.compile(r"[A-Za-z0-9_.-]+-working-container(?:-[0-9]+)?$")
IDENT = re.compile(r"[0-9a-f]{12,64}$")


def command(argv, env):
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=45).stdout.strip()


def clean_stopped_build(root, env):
    """Return traceable cleanup only after the single PX build exits."""
    if (Path(root).resolve() != ROOT or
            env.get("CONTAINERS_STORAGE_CONF") != str(ROOT / "storage.conf")):
        raise ValueError("not dedicated experimental storage")
    graph = command(["podman", "info", "--format", "{{.Store.GraphRoot}}"], env)
    if graph != STORE:
        raise ValueError("unexpected rootless graphroot")
    if command(["podman", "ps", "-a", "--format", "{{.ID}}"], env):
        raise RuntimeError("active or regular containers in dedicated store")
    lines = command(["podman", "ps", "-a", "--external",
                     "--format", "{{.ID}}|{{.Names}}|{{.Status}}"], env)
    entries = []
    for line in lines.splitlines():
        fields = line.split("|")
        if (len(fields) != 3 or not IDENT.fullmatch(fields[0]) or
                not NAME.fullmatch(fields[1]) or fields[2] != "Storage"):
            raise RuntimeError("unrecognized external container; stop cleanup")
        entries.append((fields[0], fields[1]))
    for identifier, _ in entries:
        command(["podman", "rm", "-f", identifier], env)
    still = command(["podman", "ps", "-a", "--external",
                     "--format", "{{.ID}}"], env)
    if still:
        raise RuntimeError("orphaned external build containers remain")
    allocated = command(["podman", "unshare", "du", "-sB1",
                         "/workspace/ivanka-exploratory-podman-20261121"], env)
    used = int(allocated.split()[0])
    return {"removed_external_build_containers": entries,
            "dedicated_store_bytes_after_cleanup": used}
