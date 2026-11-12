"""Capture immutable SHA256s of all seven installed assembler executables."""
import argparse
import json
from pathlib import Path

from .adapters import require_programs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--path", action="append", default=[], metavar="PROGRAM=PATH",
                        help="Override an individual executable path")
    args = parser.parse_args()
    overrides = {}
    for item in args.path:
        if "=" not in item:
            parser.error("--path requires PROGRAM=PATH")
        name, path = item.split("=", 1)
        overrides[name] = path
    found = require_programs(paths=overrides)
    result = {"schema": "ivanka.expanded.binary_pins.v1",
              "paths": {k: item["path"] for group in found.values()
                        for k, item in group.items()},
              "binary_provenance": found}
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"PINNED_TOOL_BINARIES assemblers={len(found)}")


if __name__ == "__main__":
    main()
