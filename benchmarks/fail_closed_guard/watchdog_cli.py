"""Permanent entry point for the independent s6-supervised watchdog."""
import argparse
import json
import os

from . import watchdog
from .errors import GuardExceeded


def free_bytes(root):
    """Unprivileged free bytes on the project store filesystem."""
    stat = os.statvfs(str(root))
    return stat.f_bavail * stat.f_frsize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="project lease/evidence root")
    parser.add_argument("--storage-conf", required=True)
    parser.add_argument("--graphroot", required=True)
    parser.add_argument("--stop", default=None,
                        help="boundary request; never disables a live arm")
    parser.add_argument("--min-free", type=int,
                        default=watchdog.DEFAULT_MIN_FREE)
    parser.add_argument("--reserve", type=int, default=watchdog.DEFAULT_RESERVE)
    parser.add_argument("--rss-limit", type=int, default=watchdog.RSS_LIMIT)
    parser.add_argument("--wall-seconds", type=int,
                        default=watchdog.DEFAULT_WALL_SECONDS)
    parser.add_argument("--max-age", type=float,
                        default=watchdog.DEFAULT_HEARTBEAT_MAX_AGE)
    parser.add_argument("--interval", type=float,
                        default=watchdog.DEFAULT_INTERVAL)
    parser.add_argument("--ticks", type=int, default=None,
                        help="bounded source validation only; not a deploy mode")
    args = parser.parse_args(argv)
    try:
        outcome = watchdog.supervise(
            args.root, storage_conf=args.storage_conf,
            graphroot=args.graphroot, env=os.environ.copy(),
            stop_path=args.stop, ticks=args.ticks, interval=args.interval,
            min_free=args.min_free, reserve=args.reserve,
            rss_limit=args.rss_limit, wall_seconds=args.wall_seconds,
            max_age=args.max_age,
            measure=lambda: free_bytes(args.root))
    except GuardExceeded as exc:
        print(json.dumps({"result": "fail_closed", "reason": exc.reason,
                          "evidence": getattr(exc, "evidence", None)},
                         sort_keys=True, default=str))
        return 1
    print(json.dumps(outcome, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
