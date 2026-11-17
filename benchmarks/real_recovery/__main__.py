"""CLI for separate 50-minute physical recovery after original completion."""
import argparse
import json
from pathlib import Path

from .runner import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("data", "out", "original", "images",
                   "fork", "base", "attestation"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    images = json.loads(Path(args.images).read_text())
    run(args.data, args.out, args.original, images, args.fork,
        args.base, args.attestation, args.jobs)


if __name__ == "__main__":
    main()
