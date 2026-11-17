"""Append-only container-identity observations, external to frozen scoring."""
from datetime import datetime, timezone
import json
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def update(record, measurement):
    rss, pss, processes = measurement
    record["samples"] += 1
    record["peak_tree_rss_bytes_sampled"] = max(
        record["peak_tree_rss_bytes_sampled"], rss)
    if pss is not None:
        record["pss_samples"] += 1
        record["peak_tree_pss_bytes_sampled"] = max(
            record["peak_tree_pss_bytes_sampled"], pss)
    record["max_processes_seen"] = max(record["max_processes_seen"], processes)
    record["last_observed_utc"] = now()


def create(cid, name, out=None):
    path = Path(out) / (cid + ".json") if out is not None else None
    if path is not None and path.is_file():
        record = json.loads(path.read_text())
        if (record.get("schema") != "ivanka.memory.process-tree-sampling.v1"
                or record.get("container_name") != name):
            raise ValueError("memory observation identity mismatch")
        return record
    return {"schema": "ivanka.memory.process-tree-sampling.v1",
            "container_id": cid, "container_name": name,
            "metric": "sampled-sum-of-descendant-process-resident-memory",
            "peak_tree_rss_bytes_sampled": 0,
            "peak_tree_pss_bytes_sampled": 0,
            "samples": 0, "pss_samples": 0, "max_processes_seen": 0,
            "first_observed_utc": now(), "last_observed_utc": None,
            "sampling_period_seconds": 1.0,
            "observation_ended": False}


def persist(out, record):
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (record["container_id"] + ".json")
    temp = path.with_suffix(".partial")
    temp.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    temp.replace(path)
