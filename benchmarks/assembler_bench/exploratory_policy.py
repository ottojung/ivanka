"""Fail-closed registry for NONQUALIFYING additional benchmark assemblers."""
import json
import re
from pathlib import Path

ORIGINAL = frozenset(("ivanka", "iva", "haploflow", "megahit", "abyss", "spades", "velvet"))
EXPERIMENTAL = frozenset(("skesa", "idba-ud", "minia", "ray", "unicycler",
                          "tadpole", "vicuna", "pehaplo", "penguin", "savage-denovo"))
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")


def checked(path):
    """Return a registry only if its boundary cannot change qualification."""
    data = json.loads(Path(path).read_text())
    candidates = data["candidates"]
    policy = data["policy"]
    names = [item["id"] for item in candidates]
    if (data["schema"] != "ivanka.exploratory.assemblers.v1"
            or data["qualifying"] is not False or len(names) != 10
            or set(names) != EXPERIMENTAL or len(set(names)) != len(names)
            or set(data["baseline_assemblers"]) != ORIGINAL
            or policy["total_incremental_storage_bytes"] != 8 * 1024**3
            or policy["min_workspace_free_bytes"] != 32 * 1024**3
            or policy["max_concurrent_exploratory_workers"] != 1
            or policy["max_container_wall_seconds"] != 2400
            or policy["max_sampled_process_tree_rss_bytes"] != 4_000_000_000
            or not SHA64.fullmatch(policy["frozen_seven_manifest_sha256"])):
        raise ValueError("exploratory-only roster or resource policy drift")
    for item in candidates:
        src, img = item["source_commit"], item["image_sha256"]
        if (item["qualifying"] is not False or item["status"] not in
                ("proposed", "source-pinned", "image-pinned", "pilot", "benchmarked")
                or not item["source_repo"].startswith("https://github.com/")
                or (src is not None and not SHA40.fullmatch(src))
                or (img is not None and not SHA64.fullmatch(img))
                or (item["status"] in ("image-pinned", "pilot", "benchmarked")
                    and (src is None or img is None))
                or (item["status"] == "source-pinned" and (src is None or img is not None))
                or (item["status"] == "proposed" and (src is not None or img is not None))):
            raise ValueError("unproven or qualifying explorer: " + item["id"])
    return data


def eligible(data, name):
    """No unpinned source/image may be scheduled as a result-bearing arm."""
    return next(x for x in data["candidates"] if x["id"] == name)["status"] in (
        "image-pinned", "pilot", "benchmarked")
