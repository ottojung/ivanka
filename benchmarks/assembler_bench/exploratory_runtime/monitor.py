"""Continuous best-effort disk/RSS/time monitor; never a filesystem quota."""
import subprocess
import time

from assembler_bench.exploratory_space import admit


class GuardExceeded(Exception):
    pass


def rss_group_bytes(pgid):
    result = subprocess.run(["ps", "-eo", "pgid=,rss="], check=True,
                            capture_output=True, text=True, timeout=10)
    return sum(int(fields[1]) * 1024 for line in result.stdout.splitlines()
               if len(fields := line.split()) == 2 and int(fields[0]) == pgid)


def watch(proc, config, *, interval=1, margin=1024**3, clock=time.monotonic,
          sleep=time.sleep, measure=admit, rss=rss_group_bytes):
    """Return peak sampled RSS; raise on ANY unknown resource state."""
    if interval <= 0 or interval > 1 or margin < 1024**3:
        raise ValueError("unsafe polling interval or disk safety margin")
    start = clock()
    peak = 0
    while proc.poll() is None:
        if clock() - start >= config["wall_seconds"]:
            raise GuardExceeded("wall_limit")
        try:
            space = measure(config["registry"], config["baseline"],
                            config["root"], config["image_store"],
                            config["workspace"], margin)
        except ValueError as exc:
            # The admission checker reports a REAL cap breach as ValueError.
            # It is not an unknown measurement: preserve its disk-stop cause.
            if str(exc) == "exploration would breach disk budget or workspace reserve":
                raise GuardExceeded("disk_limit") from exc
            raise GuardExceeded("measurement_unavailable") from exc
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable") from exc
        try:
            now = rss(proc.pid)
        except Exception as exc:
            raise GuardExceeded("measurement_unavailable") from exc
        peak = max(peak, now)
        if peak > config["rss_bytes"]:
            raise GuardExceeded("observed_rss_limit")
        if space["incremental_bytes"] + margin > config["budget_bytes"]:
            raise GuardExceeded("disk_limit")
        sleep(interval)
    return peak
