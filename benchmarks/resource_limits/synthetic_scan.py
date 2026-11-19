"""Read-only classification of source-attested synthetic execution records."""
from collections import Counter
import json

from .qualification import category


TOOLS = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet", "ivanka")


def name_from_args(args):
    if not isinstance(args, list):
        return None
    for i, value in enumerate(args):
        if value == "--name" and i + 1 < len(args):
            return args[i + 1]
        if value.startswith("--name="):
            return value.split("=", 1)[1]
    return None


def summary(root, telemetry, audits):
    counts = {tool: Counter() for tool in TOOLS}
    folder = root / "phase-synthetic464"
    if not folder.is_dir():
        return {tool: {} for tool in TOOLS}
    for case in folder.iterdir():
        if not case.is_dir():
            continue
        for tool in TOOLS:
            target = case / tool / "execution.json"
            if not target.is_file():
                continue
            record = json.loads(target.read_text())
            status = record.get("status")
            if status not in ("failed", "success"):
                raise ValueError(f"unknown synthetic status {target}")
            name = name_from_args(record.get("argv"))
            peak = telemetry.get(name, {}).get("peak_tree_rss_bytes_sampled")
            wrapper = {
                "failed": status != "success",
                "arm": {"container_wall_seconds": record.get("container_wall_seconds")},
            }
            counts[tool][category(wrapper, peak, audits.get(name))] += 1
    return {tool: dict(sorted(c.items())) for tool, c in counts.items()}
