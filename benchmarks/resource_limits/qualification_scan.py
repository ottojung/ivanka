"""Read-only counters for physical arms under current resource-policy evidence."""
from collections import Counter
import json
from pathlib import Path

from .qualification import category, container_name
from .synthetic_scan import summary as synthetic_summary


def load_jsonl(path, unique=True):
    if not path.exists():
        return []
    raw = path.read_bytes().splitlines(keepends=True)
    if any(not x.endswith(b"\n") for x in raw):
        raise ValueError(f"incomplete journal {path}")
    rows = [json.loads(x) for x in raw if x.strip()]
    ids = [(r.get("sample"), r.get("tool")) for r in rows]
    if unique and len(ids) != len(set(ids)):
        raise ValueError(f"duplicate arm in {path}")
    return rows


def resource_indexes(root):
    telemetry = {}
    for p in (root / "phase-resources").glob("*.json"):
        x = json.loads(p.read_text())
        name = x.get("container_name")
        if name:
            telemetry[name] = x
    audit = {}
    for x in load_jsonl(root / "cap-40m-4gb-invocations.jsonl", unique=False):
        name = x.get("container")
        if name:
            audit[name] = x
    return telemetry, audit


def report(root):
    root = Path(root)
    telemetry, audits = resource_indexes(root)
    results = {}
    for phase in ("phase-real198", "phase-real198-memory-retries"):
        by_tool = {}
        for tool in ("iva", "haploflow", "megahit", "abyss", "spades", "velvet"):
            counts = Counter()
            for row in load_jsonl(root / phase / tool / "results.jsonl"):
                name = container_name(row)
                source = telemetry.get(name, {})
                counts[category(row, source.get("peak_tree_rss_bytes_sampled"),
                                audits.get(name))] += 1
            by_tool[tool] = dict(sorted(counts.items()))
        results[phase] = by_tool
    results["phase-synthetic464"] = synthetic_summary(root, telemetry, audits)
    return {"schema": "ivanka.external-caps-qualification.v1",
            "max_wall_seconds": 2400, "max_rss_bytes": 4_000_000_000,
            "note": "Sampled RSS is not an exact kernel hard cap; no legacy success is silently requalified.",
            "results": results}
