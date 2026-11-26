"""Recover Buildah storage orphans only in the pinned project store.

Buildah ``--external`` work containers survive successful and failed builds,
are invisible to ordinary ``podman ps`` and block later trusted image builds.
This helper never guesses a container from a listing: it verifies the store
namespace, refuses any regular or unrecognised external container, removes only
the exact named storage orphans, and re-lists to prove their absence.
"""
import re
import subprocess

from . import store
from .errors import GuardExceeded

IDENT = re.compile(r"[0-9a-f]{12,64}\Z")
WORK = re.compile(r"[A-Za-z0-9_.-]+-working-container(?:-[0-9]+)?\Z")


def command(argv, env, timeout=45):
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def _external(env, command_fn):
    lines = command_fn(["podman", "ps", "-a", "--external",
                        "--format", "{{.ID}}|{{.Names}}|{{.Status}}"], env)
    entries = []
    for line in lines.splitlines():
        fields = line.split("|")
        if (len(fields) != 3 or not IDENT.fullmatch(fields[0])
                or not WORK.fullmatch(fields[1]) or fields[2] != "Storage"):
            raise GuardExceeded("orphan_unrecognized")
        entries.append({"id": fields[0], "name": fields[1],
                        "status": fields[2]})
    return entries


def clean_pinned_storage(env, graphroot, *, command_fn=None):
    """Remove only recognised storage orphans; return fresh absence evidence."""
    run = command_fn or command
    store.verify_namespace(env, graphroot)
    regular = run(["podman", "ps", "-a", "--format", "{{.ID}}"], env)
    if regular.strip():
        raise GuardExceeded("orphan_regular_container_present")
    entries = _external(env, run)
    for item in entries:
        run(["podman", "rm", "-f", item["id"]], env)
    remaining = _external(env, run)
    if remaining:
        raise GuardExceeded("orphan_cleanup_unverified")
    return {"graphroot": str(graphroot), "method": "exact_storage_orphan_ids",
            "removed": entries, "fresh_absence_check": True,
            "kernel_enforcement": False}
