"""Single-worker, source-checked nonqualifying exploratory job launcher."""
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

from assembler_bench.exploratory_policy import checked, eligible
from assembler_bench.exploratory_space import admit
from .monitor import GuardExceeded, watch
from .terminate import group


def operate(registry_path, baseline_path, tool, mode, argv, reserve_bytes):
    """Protect all new jobs with one lock and live disk/resource watching."""
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
    if root / "storage.conf" != Path(reg["policy"]["dedicated_podman_storage_conf"]):
        raise ValueError("wrong project storage configuration")
    with (root / ".global-worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        admit(reg, base, root, base["image_store"], base["workspace"], reserve_bytes)
        record = root / ("run-" + tool + "-" + str(time.time_ns()) + ".json")
        env = {**os.environ,
               "CONTAINERS_STORAGE_CONF": str(root / "storage.conf")}
        config = {"registry": reg, "baseline": base, "root": root,
                  "image_store": base["image_store"], "workspace": base["workspace"],
                  "budget_bytes": reg["policy"]["total_incremental_storage_bytes"],
                  "rss_bytes": reg["policy"]["max_sampled_process_tree_rss_bytes"],
                  "wall_seconds": reg["policy"]["max_container_wall_seconds"]}
        proc = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        state = {"tool": tool, "mode": mode, "status": "unknown", "peak_rss": None}
        try:
            state["peak_rss"] = watch(proc, config)
            state["status"] = "finished" if proc.returncode == 0 else "failed"
        except GuardExceeded as exc:
            state["status"] = "killed"
            state["reason"] = str(exc)
        finally:
            state["exit_code"] = group(proc)
            state["recorded_utc"] = time.time()
            with record.open("x") as out:
                json.dump(state, out, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
        return state
