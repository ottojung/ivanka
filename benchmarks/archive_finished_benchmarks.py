"""Losslessly archive generated scratch files only after a sample is terminal.

This is an auxiliary benchmark resource-management process, never a scorer.
It uses the checksum-verified archive utility and leaves patient FASTQs,
all final CSVs and the JSONL evidence untouched.
"""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import time


def terminal_artifacts(root, records):
    root = Path(root).resolve()
    results = []
    for record in records:
        if record.get("status") == "started":
            continue
        for arm in ("iva", "ivanka"):
            artifact = record.get(arm, {}).get("artifact_dir")
            if not isinstance(artifact, str) or not artifact:
                continue
            path = Path(artifact).resolve()
            if root not in path.parents or not path.is_dir():
                raise ValueError("Invalid result artifact path")
            if not (path / "scratch").is_dir():
                continue
            results.append(path)
    return sorted(set(results))


def read_records(file):
    records = []
    if file.exists():
        raw = file.read_bytes()
        # A concurrently appended final JSONL row may be incomplete.
        # Ignore that row until its terminating newline is visible.
        if raw and not raw.endswith(b"\n"):
            raw = raw[:raw.rfind(b"\n") + 1]
        for line in raw.splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def load_archiver(script):
    spec = importlib.util.spec_from_file_location("scratch_archive", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process(root, archive, seen, script):
    current = terminal_artifacts(root, read_records(Path(root) / "results.jsonl"))
    module = load_archiver(script)
    for artifact in current:
        rel = artifact.relative_to(Path(root).resolve()).as_posix()
        if rel in seen:
            continue
        module.ROOT = artifact
        module.MANIFEST = Path(archive)
        module.run()
        seen.add(rel)
        with Path(str(archive) + ".completed").open("a") as out:
            out.write(rel + "\n")
            out.flush()
    return len(current)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archiver", type=Path,
                        default=Path("/workspace/ivanka-k1-lossless-scratch-archive-20261110.py"))
    parser.add_argument("--expected", type=int, default=198)
    parser.add_argument("--poll", type=int, default=15)
    args = parser.parse_args()
    root = args.results.resolve()
    if not root.is_dir() or args.expected < 1 or args.poll < 1:
        raise ValueError("Invalid archive watcher arguments")
    with (root / ".scratch-archive.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        completed = Path(str(args.archive) + ".completed")
        seen = set(completed.read_text().splitlines()) if completed.exists() else set()
        while True:
            artifacts = process(root, args.archive, seen, args.archiver)
            records = read_records(root / "results.jsonl")
            terminal = [r for r in records if r.get("status") != "started"]
            print("WATCH_ARCHIVE", len(terminal), "/", args.expected,
                  "ARTIFACTS", artifacts, "SEEN", len(seen), flush=True)
            if len(terminal) >= args.expected:
                print("ARCHIVE_WATCH_DONE", flush=True)
                return
            time.sleep(args.poll)


if __name__ == "__main__":
    main()
