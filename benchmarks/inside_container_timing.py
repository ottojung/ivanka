"""Measure the MiCall command *inside* the image; never include Podman setup/teardown.

Executed by the benchmark as the container's timed child. Only a successful
MiCall subprocess and an atomic timing record authorize a runtime measurement.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

TIMING_ORIGIN = "micall_in_container_monotonic_v1"


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: inside_container_timing.py OUTPUT COMMAND [ARG...]")
    destination = Path(sys.argv[1])
    start = time.monotonic_ns()
    status = subprocess.call(sys.argv[2:])
    elapsed = (time.monotonic_ns() - start) / 1_000_000_000
    temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps({
            "timing_origin": TIMING_ORIGIN, "seconds": elapsed,
            "exit_code": status,
        }, sort_keys=True))
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
