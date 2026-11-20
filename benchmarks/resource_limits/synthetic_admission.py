"""External resource-based synthetic worker admission; clinical source unchanged."""
from pathlib import Path
import sys

CGROUP = Path("/sys/fs/cgroup")
GB = 1024**3


def choose(maximum, current, inactive_file):
    if (maximum <= 0 or current < 0 or inactive_file < 0
            or inactive_file > current):
        raise ValueError("invalid cgroup counters")
    raw = maximum - current
    reclaimable = raw + inactive_file
    if raw >= 8 * GB and reclaimable >= 12 * GB:
        return 3
    if raw >= 0 and reclaimable >= 8 * GB:
        return 2
    raise OSError("cgroup headroom insufficient for guarded two-arm MiCall")


def read_choice():
    try:
        maximum = int((CGROUP / "memory.max").read_text().strip())
        current = int((CGROUP / "memory.current").read_text().strip())
        stat = dict(line.split() for line in
                    (CGROUP / "memory.stat").read_text().splitlines())
        return choose(maximum, current, int(stat["inactive_file"]))
    except (ValueError, KeyError, OSError) as exc:
        raise OSError("cannot certify two/three worker cgroup admission") from exc


def main():
    try:
        print(read_choice())
    except OSError as exc:
        print(f"SYNTHETIC_WORKER_CAPACITY_PAUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
