"""Prove ownership of exact Buildah storage containers, never sweep broadly."""
import re
import subprocess

from . import store
from .errors import GuardExceeded

IDENT = re.compile(r"[0-9a-f]{12,64}\Z")
STORAGE = "Storage"


def command(argv, env, timeout=45):
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def _external(env, run):
    lines = run(["podman", "ps", "-a", "--external",
                 "--format", "{{.ID}}|{{.Names}}|{{.Status}}"], env)
    entries = {}
    for line in lines.splitlines():
        fields = line.split("|")
        if len(fields) != 3 or not IDENT.fullmatch(fields[0]):
            raise GuardExceeded("orphan_unrecognized")
        entries[fields[0]] = {"id": fields[0], "name": fields[1],
                              "status": fields[2]}
    return entries


def capture_baseline(env, graphroot, *, command_fn=None):
    """Record the exact external IDs that existed before this job."""
    run = command_fn or command
    store.verify_namespace(env, graphroot)
    regular = run(["podman", "ps", "-a", "--format", "{{.ID}}"], env)
    if regular.strip():
        raise GuardExceeded("orphan_regular_container_present")
    return _external(env, run)


def reclaim_owned(env, graphroot, baseline, *, expected_name, command_fn=None):
    """Remove only exact new IDs owned by this job; prove their absence."""
    run = command_fn or command
    store.verify_namespace(env, graphroot)
    regular = run(["podman", "ps", "-a", "--format", "{{.ID}}"], env)
    if regular.strip():
        raise GuardExceeded("orphan_regular_container_present")
    current = _external(env, run)
    added = {key: value for key, value in current.items() if key not in baseline}
    changed = [key for key in baseline
               if key in current and current[key] != baseline[key]]
    missing = [key for key in baseline if key not in current]
    if changed or missing:
        raise GuardExceeded("orphan_baseline_changed")
    for item in added.values():
        if (item["status"] != STORAGE
                or item["name"] != expected_name
                or not IDENT.fullmatch(item["id"])):
            raise GuardExceeded("orphan_unowned")
    for item in added.values():
        run(["podman", "rm", "-f", item["id"]], env)
    after = _external(env, run)
    if any(key in after for key in added) or set(after) != set(baseline):
        raise GuardExceeded("orphan_cleanup_unverified")
    return {"graphroot": str(graphroot), "method": "exact_owned_external_ids",
            "expected_name": expected_name,
            "baseline_ids": sorted(baseline), "removed": list(added.values()),
            "fresh_absence_check": True, "kernel_enforcement": False}
