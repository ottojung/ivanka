"""Validate unqualified job and rooted Podman store before process spawn."""
import configparser
import hashlib
import json
from pathlib import Path

from assembler_bench.exploratory_policy import checked, eligible


def prepare(registry_path, baseline_path, tool, mode, argv, reserve_bytes):
    reg = checked(registry_path)
    base = json.loads(Path(baseline_path).read_text())
    row = next((x for x in reg["candidates"] if x["id"] == tool), None)
    if (row is None or mode not in ("build", "pilot") or not argv
            or reserve_bytes < 1024**3 or reserve_bytes > 4 * 1024**3
            or (mode == "build" and row["status"] != "source-pinned")
            or (mode == "pilot" and not eligible(reg, tool))
            or any(a in ("--detach", "-d") for a in argv)):
        raise ValueError("not an admissible bounded nonqualifying job")
    root = Path(base["root"])
    storage = root / "storage.conf"
    store = Path(base["image_store"]).resolve()
    if (storage != Path(reg["policy"]["dedicated_podman_storage_conf"])
            or store != Path(reg["policy"]["dedicated_image_store_root"])
            or hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest()
            != reg["storage_baseline_sha256"]):
        raise ValueError("wrong project storage or changed disk baseline")
    policy = configparser.ConfigParser()
    if not policy.read(storage) or dict(policy["storage"]) != {
            "driver": "overlay", "graphroot": str(store / "store"),
            "runroot": str(store / "run")}:
        raise ValueError("invalid dedicated-only container storage config")
    cfg = {"registry": reg, "baseline": base, "root": root,
           "image_store": base["image_store"], "workspace": base["workspace"],
           "budget_bytes": reg["policy"]["total_incremental_storage_bytes"],
           "rss_bytes": reg["policy"]["max_sampled_process_tree_rss_bytes"],
           "wall_seconds": reg["policy"]["max_container_wall_seconds"]}
    return root, base, reg, cfg
