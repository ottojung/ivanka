"""Reclaim reproducible MiCall scratch only after full checkpoint verification."""
import argparse
import json
from pathlib import Path
import re
import shutil
import time

from .micall_checkpoint import existing_case


def prune_case(root, row, images, truth):
    """Validate every arm before removing scratch from successful ones."""
    identifier = row["id"]
    if not re.fullmatch(r"[a-z0-9_-]+", identifier):
        raise ValueError("invalid benchmark case identifier")
    if row["truth_validation"] != truth:
        raise ValueError("case truth provenance differs from pinned cohort")
    fields = {key: row[key] for key in
              ("id", "cohort", "family", "truth_validation", "input_sha256")}
    folder = Path(root) / identifier
    if existing_case(folder, fields, images) != row:
        raise ValueError("mismatched committed case checkpoint")
    cleaned = 0
    for name, result in row["results"].items():
        scratch = folder / name / "scratch"
        if result["status"] != "success" or not scratch.exists():
            continue  # Failed arms retain exploratory scratch for diagnosis.
        if not scratch.is_dir() or scratch.is_symlink():
            raise ValueError("scratch is not a real directory")
        shutil.rmtree(scratch)
        cleaned += 1
    return cleaned


def prune_completed(root):
    """Keep final CSVs, stderr, timing and immutable evidence for every arm."""
    root = Path(root)
    manifest = json.loads((root / "run_manifest.json").read_text())
    records = (root / "results.jsonl").read_text().splitlines(keepends=True)
    seen = set()
    deleted = 0
    for line in records:
        if not line.endswith("\n"):
            break  # Concurrent append is not a committed record.
        row = json.loads(line)
        if row["id"] in seen:
            raise ValueError("duplicate benchmark case identifier")
        seen.add(row["id"])
        deleted += prune_case(root, row, manifest["images"],
                              manifest["source_truth"])
    return len(seen), deleted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--watch-pid", type=int)
    args = parser.parse_args()
    while True:
        cases, cleaned = prune_completed(args.root)
        print(f"CHECKPOINTED={cases} SCRATCH_DIRS_RECLAIMED={cleaned}", flush=True)
        if not args.follow or (args.root / "attempt_completion.json").exists():
            break
        if args.watch_pid and not Path(f"/proc/{args.watch_pid}").exists():
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
