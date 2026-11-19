"""External source-pinned 40-minute, 4-GB Podman policy enforcement.

For MiCall benchmark containers only; all other Podman calls are forwarded.
"""
import json
import os
import sys

from benchmarks.resource_limits.podman_args import (
    CAP_BYTES, CAP_SECONDS, capped, option,
)

REAL_PODMAN = "/var/guix/profiles/per-user/puser/guix-profile/bin/podman"


def main():
    args = sys.argv[1:]
    updated, changed = capped(args)
    if changed:
        path = os.environ.get("IVANKA_CAP_AUDIT_LOG")
        if not path:
            raise ValueError("benchmark requires independent cap audit log")
        _, name = option(updated, "--name")
        _, timer = option(updated, "--timeout")
        record = {
            "schema": "ivanka.external-caps.v1",
            "container": name, "podman_action": updated[0],
            "podman_timeout_seconds": int(timer),
            "max_wall_seconds": CAP_SECONDS, "memory_max_bytes": CAP_BYTES,
            "original_requested_timeout": option(args, "--timeout")[1],
            "image": next((x for x in updated if len(x) == 64
                           and all(y in "0123456789abcdef" for y in x)), None),
        }
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
    os.execv(REAL_PODMAN, [REAL_PODMAN, *updated])


if __name__ == "__main__":
    main()
