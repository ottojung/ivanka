"""Fail-closed DISK ADMISSION CHECK, not a running-job quota/watcher."""
import os
import re
import subprocess
import time
from pathlib import Path

# This is the ONLY dedicated rootless store authorized by the PX policy.
# Podman overlay subdirectories are remapped to container UIDs: ordinary
# host 'du' returns permission errors while an image build is in progress.
ROOTLESS_STORE = Path("/workspace/ivanka-exploratory-podman-20261121")
PROJECT_ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
PROJECT_TMP = PROJECT_ROOT / "tmp"
# A live Buildah overlay can vanish between du's readdir and its stat.
# Retry ONLY this exact, ephemeral ENOENT; permissions and all other failures
# remain fail-closed rather than publishing partial disk measurements.
TEMP_DIR_DISAPPEARED = re.compile(
    r"du: fts_read failed: " + re.escape(str(ROOTLESS_STORE))
    + r"/store/overlay(?:/tempdirs/temp-dir-[0-9]+/[^\n:]+)?"
    + r": No such file or directory\n?"
)
DPKG_RENAME_DISAPPEARED = re.compile(
    r"(?:du: cannot access '" + re.escape(str(ROOTLESS_STORE))
    + r"/store/overlay/[0-9a-f]{64}/diff/[^'\n]+\.dpkg-new':"
    + r" No such file or directory\n?)+"
)
TEMP_NAME = "tmp"


def px_temp_dir(root):
    """Return the project-owned directory that receives all job temporaries."""
    return Path(root).resolve() / TEMP_NAME


def allocated_optional(path):
    """Count a measured path that may not exist yet, failing closed if unreadable."""
    target = Path(path)
    return allocated(target) if target.is_dir() else 0


def disk_measure_command(target):
    """Count every allocated block or fail closed; never parse partial 'du'."""
    command = ["du", "-sB1", "--", str(target)]
    if target in (ROOTLESS_STORE, PROJECT_ROOT, PROJECT_TMP):
        # The OCI store, project root and its TMPDIR contain Buildah mounts.
        # During apt installs, project/tmp/buildah*/mnt can be inaccessible to
        # host du. A rootless user namespace with -x skips only mounted virtual
        # root filesystems while counting actual writable OCI layers and TMPDIR.
        # This is read-only and scoped to exactly the two isolated PX roots.
        return ["podman", "unshare", "du", "-sxB1", "--", str(target)]
    return command


def allocated(path):
    """Use exact allocated blocks, including rootless Podman overlay layers."""
    target = Path(path).resolve()
    if not target.is_dir():
        raise ValueError("missing measured directory: " + str(target))
    for attempt in range(3):
        try:
            result = subprocess.run(disk_measure_command(target), check=True,
                                    text=True, capture_output=True, timeout=15)
            return int(result.stdout.split()[0])
        except subprocess.CalledProcessError as error:
            if (target != ROOTLESS_STORE or attempt == 2
                    or not isinstance(error.stderr, str)
                    or not (TEMP_DIR_DISAPPEARED.fullmatch(error.stderr)
                            or DPKG_RENAME_DISAPPEARED.fullmatch(error.stderr))):
                raise
            time.sleep(0.1)
    raise RuntimeError("unreachable disk accounting retry state")


def available(path):
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize


def admit(registry, baseline, root, image_store, workspace, proposed_bytes):
    """Assess free space + total new OCI layers + retained exploration data."""
    cfg = registry["policy"]
    if (baseline["schema"] != "ivanka.exploratory.storage-baseline.v1"
            or baseline["root"] != str(Path(root).resolve())
            or baseline["image_store"] != str(Path(image_store).resolve())
            or baseline["workspace"] != str(Path(workspace).resolve())
            or str(Path(image_store).resolve()) != cfg["dedicated_image_store_root"]
            or baseline["frozen_manifest_sha256"] != cfg["frozen_seven_manifest_sha256"]
            or not isinstance(proposed_bytes, int) or proposed_bytes < 1
            or baseline.get("active_job") is not None):
        raise ValueError("invalid or concurrently active exploration admission")
    extra_layers = max(0, allocated(image_store) - baseline["base_store_bytes"])
    retained_all = allocated(root)
    # Podman image imports and builds spill large temporary layers into TMPDIR.
    # The launcher redirects those files into the project-owned temp directory;
    # count them explicitly and clamp against the parent total to avoid double-counting
    # temporaries already included in the project total.
    temp_bytes = min(allocated_optional(px_temp_dir(root)), retained_all)
    retained = retained_all - temp_bytes
    used, free = retained + temp_bytes + extra_layers, available(workspace)
    if (used + proposed_bytes > cfg["total_incremental_storage_bytes"]
            or free - proposed_bytes < cfg["min_workspace_free_bytes"]):
        raise ValueError("exploration would breach disk budget or workspace reserve")
    return {"retained_bytes": retained, "temp_bytes": temp_bytes,
            "new_image_bytes": extra_layers, "incremental_bytes": used,
            "free_bytes": free, "admitted_reservation_bytes": proposed_bytes}


def initial(root, image_store, workspace, registry):
    """Record before creating ANY exploratory images; require an empty root."""
    target = Path(root).resolve()
    if not target.is_dir() or any(target.iterdir()):
        raise ValueError("admission baseline must start with an empty project root")
    cfg = registry["policy"]
    free = available(workspace)
    if free < cfg["min_workspace_free_bytes"] + cfg["total_incremental_storage_bytes"]:
        raise ValueError("not enough space to reserve the complete exploration budget")
    return {"schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(target), "image_store": str(Path(image_store).resolve()),
            "workspace": str(Path(workspace).resolve()),
            "base_store_bytes": allocated(image_store),
            "frozen_manifest_sha256": cfg["frozen_seven_manifest_sha256"],
            "active_job": None}
