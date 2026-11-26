"""Prove ownership of exact Buildah storage containers, never sweep broadly."""
import json
import re
import subprocess

from . import store
from .errors import GuardExceeded


def normalize(value):
    """Podman reports sha256:<digest>; compare only exact bare hex."""
    if isinstance(value, str):
        bare = value.strip().removeprefix("sha256:").lower()
        if FULL.fullmatch(bare):
            return bare
    raise GuardExceeded("orphan_inspect_unavailable")

FULL = re.compile(r"[0-9a-f]{64}\Z")
STORAGE = "Storage"
EXTERNAL_FORMAT = "{{.ID}}|{{.Names}}|{{.Status}}"
INSPECT_FORMAT = "{{.Image}}|{{.Name}}|{{json .RootFS.Layers}}"


def command(argv, env, timeout=45):
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def _external(env, run):
    # --no-trunc is mandatory: a 12-hex prefix is not an owned identity.
    lines = run(["podman", "ps", "-a", "--external", "--no-trunc",
                 "--format", EXTERNAL_FORMAT], env)
    entries = {}
    for line in lines.splitlines():
        fields = line.split("|")
        if len(fields) != 3 or not FULL.fullmatch(fields[0]):
            raise GuardExceeded("orphan_unrecognized")
        entries[fields[0]] = {"id": fields[0], "name": fields[1],
                              "status": fields[2]}
    return entries


def capture_baseline(env, graphroot, *, command_fn=None):
    """Record exact full external IDs that existed before this job."""
    run = command_fn or command
    store.verify_namespace(env, graphroot)
    regular = run(["podman", "ps", "-a", "--no-trunc", "--format",
                   "{{.ID}}"], env)
    if regular.strip():
        raise GuardExceeded("orphan_regular_container_present")
    return _external(env, run)


def base_working_name(base):
    """Buildah names a working container from its base image, not our lease."""
    return base[:12] + "-working-container"


def inspect_external(env, identifier, *, command_fn=None):
    """Inspect one exact external container and prove its base derivation."""
    run = command_fn or command
    fields = run(["podman", "inspect", "--format", INSPECT_FORMAT,
                  identifier], env).split("|")
    if len(fields) != 3:
        raise GuardExceeded("orphan_inspect_unavailable")
    image = normalize(fields[0].strip())
    try:
        layers = json.loads(fields[2])
    except ValueError as exc:
        raise GuardExceeded("orphan_inspect_unavailable") from exc
    if not isinstance(layers, list):
        raise GuardExceeded("orphan_inspect_unavailable")
    return {"image": image, "name": fields[1].strip(),
            "layers": [normalize(item) for item in layers]}


def reclaim_owned(env, graphroot, baseline, *, expected_base, base_layers=None,
                  command_fn=None):
    """Remove only exact new IDs proved to derive from the pinned base."""
    run = command_fn or command
    store.verify_namespace(env, graphroot)
    regular = run(["podman", "ps", "-a", "--no-trunc", "--format",
                   "{{.ID}}"], env)
    if regular.strip():
        raise GuardExceeded("orphan_regular_container_present")
    current = _external(env, run)
    known = set(baseline.keys() if isinstance(baseline, dict) else baseline)
    added = {key: value for key, value in current.items() if key not in known}
    if any(key not in current for key in known):
        raise GuardExceeded("orphan_baseline_changed")
    if (isinstance(baseline, dict)
            and any(current[key] != baseline[key] for key in known)):
        raise GuardExceeded("orphan_baseline_changed")
    base = normalize(expected_base)
    expected_name = base_working_name(base)
    for identifier, item in added.items():
        if (item["status"] != STORAGE or item["name"] != expected_name
                or not FULL.fullmatch(identifier)):
            raise GuardExceeded("orphan_unowned")
        proof = inspect_external(env, identifier, command_fn=run)
        if proof["image"] != base or proof["name"] != expected_name:
            raise GuardExceeded("orphan_unowned")
        if base_layers is not None:
            layers = proof["layers"]
            expected_layers = [normalize(item) for item in base_layers]
            if (layers[:len(expected_layers)] != expected_layers
                    or len(layers) != len(expected_layers) + 1):
                raise GuardExceeded("orphan_unowned")
        item["inspect"] = proof
    for identifier in added:
        run(["podman", "rm", "-f", identifier], env)
    after = _external(env, run)
    if any(key in after for key in added) or set(after) != known:
        raise GuardExceeded("orphan_cleanup_unverified")
    return {"graphroot": str(graphroot), "method": "exact_full_id_base_proof",
            "expected_base": base,
            "expected_name": expected_name,
            "baseline_ids": sorted(known), "removed": list(added.values()),
            "fresh_absence_check": True, "kernel_enforcement": False}
