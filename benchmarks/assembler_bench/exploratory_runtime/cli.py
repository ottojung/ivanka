"""Operate one bounded exploratory image build or source-attested pilot."""
import argparse
from pathlib import Path

from .launch import operate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--tool", required=True)
    p.add_argument("--mode", choices=("build", "pilot"), required=True)
    p.add_argument("--reserve-bytes", type=int, required=True)
    p.add_argument("argv", nargs=argparse.REMAINDER)
    a = p.parse_args()
    if not a.argv or a.argv[0] != "--":
        p.error("the executable arguments must follow --")
    status = operate(a.registry, a.baseline, a.tool, a.mode,
                     a.argv[1:], a.reserve_bytes)
    print(status, flush=True)
    return 0 if status["status"] == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
