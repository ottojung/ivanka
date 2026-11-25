#!/usr/bin/env python3
"""Rotate one single-writer benchmark audit log, retaining verified bytes."""
import argparse
import gzip
import hashlib
import os
import time
from pathlib import Path


def digest(path, opener=open):
    with opener(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_pending(pending):
    """On interruption retain the original pending file until verified."""
    final = pending.with_suffix(".gz")
    sidecar = pending.with_suffix(".sha256")
    temporary = final.with_suffix(".gz.partial")
    expected = digest(pending)
    if final.exists():
        if digest(final, gzip.open) != expected:
            raise ValueError("existing archive disagrees with pending log")
    else:
        with pending.open("rb") as source, temporary.open("wb") as out:
            with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=1,
                               mtime=0) as zipped:
                while block := source.read(1024 * 1024):
                    zipped.write(block)
            out.flush()
            os.fsync(out.fileno())
        if digest(temporary, gzip.open) != expected:
            raise ValueError("archive content does not match original")
        os.replace(temporary, final)
    with sidecar.open("w") as stream:
        stream.write(expected + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Persist both directory entries before discarding the original.
    fd = os.open(pending.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
        pending.unlink()
        os.fsync(fd)
    finally:
        os.close(fd)


def rotate(log, directory, threshold=16 * 1024**2):
    log, directory = Path(log), Path(directory)
    if threshold < 1 or log.is_symlink() or directory.is_symlink():
        raise ValueError("unsafe audit log rotation")
    directory.mkdir(parents=True, exist_ok=True)
    if log.exists() and log.is_file() and log.stat().st_size >= threshold:
        pending = directory / ("retention-%d.jsonl.pending" % time.time_ns())
        os.rename(log, pending)
    for pending in sorted(directory.glob("retention-*.jsonl.pending")):
        if pending.is_symlink() or not pending.is_file():
            raise ValueError("unsafe pending audit log")
        archive_pending(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    rotate(args.log, args.directory)


if __name__ == "__main__":
    main()
