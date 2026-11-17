"""CLI for 50-minute synthetic phase with 5 GiB per arm."""
import argparse
import json
from pathlib import Path

from .synthetic_runner import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("data", "out", "images", "fork", "base", "attestation"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--jobs", type=int, default=5)
    args = parser.parse_args()
    images = json.loads(Path(args.images).read_text())
    run(args.data, args.out, images, args.fork, args.base,
        args.attestation, args.jobs)


if __name__ == "__main__":
    main()
