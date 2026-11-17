"""Verify both original 30-minute and new 50-minute synthetic records."""
import json
import math
from pathlib import Path

from benchmarks.expanded.micall_checkpoint import digest


def verify(path, tool, image):
    path = Path(path)
    record_path = path / "execution.json"
    if not record_path.is_file():
        return None
    row = json.loads(record_path.read_text())
    if (row.get("sha256") != image
            or row.get("status") not in ("success", "failed")
            or row.get("score_origin") != "micall_final_max_reference_panel_v1"
            or row.get("timing_origin") != "micall_in_container_monotonic_v1"
            or row.get("argv", []).count(image) != 1
            or row.get("argv", [])[-1] != "--all_projects"):
        raise ValueError("invalid MiCall comparator arm identity: " + tool)
    args = row["argv"]
    if (args[args.index("--timeout") + 1] not in ("1800", "3000")
            or len([x for x in args
                    if x in ("--memory=4g", "--memory=5g")]) != 1):
        raise ValueError("unrecognized comparator resource policy")
    if row["status"] == "success":
        metric = row.get("final_dominant", {})
        target = path / metric.get("source_output", "nonexistent")
        limit = int(args[args.index("--timeout") + 1])
        if (row.get("exit_code") != 0 or not target.is_file()
                or digest(target) != metric.get("conseq_csv_sha256")
                or not isinstance(row.get("seconds"), (float, int))
                or not math.isfinite(row["seconds"])
                or not 0 < row["seconds"] <= limit
                or not isinstance(row.get("score"), (float, int))
                or not math.isfinite(row["score"]) or row["score"] < 0):
            raise ValueError("invalid synthetic MiCall completion evidence")
    return row
