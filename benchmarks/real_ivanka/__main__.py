"""CLI for the source-verified 50-minute physical Ivanka phase."""
import argparse
import json
from pathlib import Path

from .runner import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "out", "original", "retries",
                 "images", "fork", "base", "attestation"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--jobs", default=2, type=int)
    args = parser.parse_args()
    images = json.loads(Path(args.images).read_text())
    run(args.data, args.out, args.original, args.retries, images, args.fork,
        args.base, args.attestation, jobs=args.jobs)


if __name__ == "__main__":
    main()
