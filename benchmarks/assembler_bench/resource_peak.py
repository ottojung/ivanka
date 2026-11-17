"""Publish only ended, named, sampled process-tree RSS, never shared cgroup RAM."""
import json
import math
from pathlib import Path


SCHEMA = "ivanka.memory.process-tree-sampling.v1"


def load(directory):
    if directory is None or not Path(directory).is_dir():
        return {}
    result = {}
    for source in sorted(Path(directory).glob("*.json")):
        record = json.loads(source.read_text())
        name = record.get("container_name")
        count = record.get("samples")
        bytes_seen = record.get("peak_tree_rss_bytes_sampled")
        if (record.get("schema") != SCHEMA
                or source.stem != record.get("container_id")
                or not isinstance(name, str)
                or not name.startswith(("ivanka-bench-ivanka-",
                                        "ivanka-bench-iva-",
                                        "ivanka-bench-synth-"))
                or type(count) is not int or count < 0
                or type(bytes_seen) is not int or bytes_seen < 0):
            raise ValueError("unverified process-tree RAM observation")
        if name in result:
            raise ValueError("same container name has conflicting memory runs")
        result[name] = record
    return result


def peak_mib(records, name):
    record = records.get(name)
    if not record or record["samples"] < 2 or not record["observation_ended"]:
        return None
    value = record["peak_tree_rss_bytes_sampled"] / 1048576
    return value if math.isfinite(value) and value > 0 else None


def physical_name(arm, tool, sample, sha_bytes):
    root = arm.get("artifact_dir")
    if not isinstance(root, str):
        return None
    identifier = Path(root).parents[1].name
    subcommand = "iva" if tool == "iva" else "ivanka"
    return f"ivanka-bench-{subcommand}-{identifier}-{sha_bytes(sample.encode())[:8]}"


def synthetic_name(record):
    args = record.get("argv", [])
    if not isinstance(args, list) or args.count("--name") != 1:
        return None
    return args[args.index("--name") + 1]
