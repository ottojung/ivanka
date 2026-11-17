"""Close interrupted monitoring intervals only after verified Podman discovery."""
import json
from pathlib import Path

from .records import now, persist


def reconcile(directory, running):
    """Finalize missing old observations; never invent an unobserved peak."""
    path = Path(directory)
    count = 0
    if not path.is_dir():
        return count
    for file in path.glob("*.json"):
        record = json.loads(file.read_text())
        if (record.get("schema") != "ivanka.memory.process-tree-sampling.v1"
                or record.get("container_id") != file.stem
                or not isinstance(record.get("container_name"), str)
                or record.get("samples", -1) < 0):
            raise ValueError("memory-observer file identity mismatch")
        if file.stem in running:
            if running[file.stem][0] != record["container_name"]:
                raise ValueError("running container identity mismatch")
            continue
        if record.get("observation_ended") is True:
            continue
        if record.get("observation_ended") is not False:
            raise ValueError("invalid memory-observer terminal field")
        record["observation_ended"] = True
        record["observation_end_cause"] = "monitor_restart_unobserved"
        record["observation_end_detected_utc"] = now()
        persist(path, record)
        count += 1
    return count
