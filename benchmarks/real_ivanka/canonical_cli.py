"""CLI to fill canonical phase-real198/ivanka without restarting competitors."""
import argparse
import json
from pathlib import Path

from .canonical import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("data", "original", "retries", "images",
                "fork", "base", "attestation"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    images = json.loads(Path(args.images).read_text())
    run(args.data, args.original, args.retries, images,
        args.fork, args.base, args.attestation, args.jobs)


if __name__ == "__main__":
    main()
