"""Low-impact persistent monitor; never modifies MiCall checkpoint evidence."""
import argparse
import logging
import time

from .containers import running
from .proc_tree import sample_tree
from .records import create, persist, update


def watch(out, period=1.0):
    active = {}
    last_discovery = 0.0
    while True:
        moment = time.monotonic()
        if moment - last_discovery >= 4:
            try:
                found = running()
                for cid, (name, pid) in found.items():
                    if cid not in active:
                        active[cid] = (pid, create(cid, name, out))
                for cid in set(active) - set(found):
                    _, record = active.pop(cid)
                    record["observation_ended"] = True
                    persist(out, record)
                last_discovery = moment
            except Exception as exc:
                logging.warning("Podman discovery deferred: %s", exc)
        for cid, (pid, record) in active.items():
            measured = sample_tree(pid)
            if measured is not None:
                update(record, measured)
                if record["samples"] % 10 == 0:
                    persist(out, record)
        time.sleep(period)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    watch(args.out)


if __name__ == "__main__":
    main()
