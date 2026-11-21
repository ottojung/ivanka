"""Fail-closed DISK ADMISSION CHECK, not a running-job quota/watcher."""
import os
import subprocess
from pathlib import Path


def allocated(path):
    """Use allocated blocks rather than logical file length."""
    target = Path(path).resolve()
    if not target.is_dir():
        raise ValueError("missing measured directory: " + str(target))
    result = subprocess.run(["du", "-sB1", "--", str(target)],
                            check=True, text=True, capture_output=True,
                            timeout=60)
    return int(result.stdout.split()[0])


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
            or baseline["frozen_manifest_sha256"] != cfg["frozen_seven_manifest_sha256"]
            or not isinstance(proposed_bytes, int) or proposed_bytes < 1
            or baseline.get("active_job") is not None):
        raise ValueError("invalid or concurrently active exploration admission")
    extra_layers = max(0, allocated(image_store) - baseline["base_store_bytes"])
    retained = allocated(root)
    used, free = retained + extra_layers, available(workspace)
    if (used + proposed_bytes > cfg["total_incremental_storage_bytes"]
            or free - proposed_bytes < cfg["min_workspace_free_bytes"]):
        raise ValueError("exploration would breach disk budget or workspace reserve")
    return {"retained_bytes": retained, "new_image_bytes": extra_layers,
            "incremental_bytes": used, "free_bytes": free,
            "admitted_reservation_bytes": proposed_bytes}


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
