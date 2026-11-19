"""Generate an isolated cap-qualification report; never alter clinical results."""
import argparse
import json
from pathlib import Path
from .qualification_scan import report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = report(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".partial")
    if tmp.exists():
        raise FileExistsError(tmp)
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.output)
    print("CAP_POLICY_REPORT", args.output)


if __name__ == "__main__":
    main()
