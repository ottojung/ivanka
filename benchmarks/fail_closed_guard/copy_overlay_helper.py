"""Gated helper: exec the reviewed build only after a durable exact bind.

The helper owns the process group for its whole life. It keeps the same kernel
task (and therefore the same starttime and PID namespace) across the final
``exec``; only the command line changes. It never builds on a pipe EOF, a
deadline, a missing or mismatched durable bind, or an unreadable identity.
"""
import argparse
import os
import select
import time

from . import lease, proc
from .errors import GuardExceeded


def stable_self(table=None):
    """Immutable kernel identity of this helper task."""
    table = proc.snapshot() if table is None else table
    record = table.get(os.getpid())
    if record is None or any(record.get(key) is None
                             for key in ("starttime", "pid_ns")):
        raise GuardExceeded("binding_unavailable")
    return (record["starttime"], record["pid_ns"])


def gate(stream, root, ident, *, graphroot, deadline, deadline_mono=None,
         clock=None, monotonic=None, select_fn=None, snapshot=None,
         sealed_context=None, base=None, artifact_sha256=None,
         artifact_mode=None):
    """Wait for permission, then re-prove bind, context and both deadlines."""
    now = clock if clock is not None else time.time
    mono = monotonic if monotonic is not None else time.monotonic
    choose = select_fn if select_fn is not None else select.select
    pid = os.getpid()
    stable = stable_self(snapshot() if snapshot is not None else None)
    remaining = max(0.0, deadline - now())
    ready, _, _ = choose([stream], [], [], remaining)
    if not ready or stream.read(1) != b"G":
        return False
    if now() >= deadline or (deadline_mono is not None
                             and mono() >= deadline_mono):
        return False
    try:
        event = lease.latest(lease.events(root)).get(str(ident))
    except GuardExceeded:
        return False
    finger = event.get("fingerprint") if event else None
    bound = bool(event and event.get("state") == "active"
                 and event.get("mode") == "copy_overlay"
                 and event.get("pid") == pid and event.get("pgid") == pid
                 and event.get("graphroot") == str(graphroot)
                 and isinstance(finger, (list, tuple)) and len(finger) >= 2
                 and tuple(finger[:2]) == stable)
    if not bound:
        return False
    if sealed_context is not None:
        from . import copy_overlay
        try:
            copy_overlay.verify_sealed(
                sealed_context, base=base, artifact_sha256=artifact_sha256,
                artifact_mode=artifact_mode)
        except GuardExceeded:
            return False
    # Verification itself may consume the whole budget; re-check before exec.
    return not (now() >= deadline or (deadline_mono is not None
                                      and mono() >= deadline_mono))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-fd", type=int, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--ident", required=True)
    parser.add_argument("--graphroot", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--deadline-monotonic", type=float, default=None)
    parser.add_argument("--context", default=None)
    parser.add_argument("--base", default=None)
    parser.add_argument("--artifact-sha256", default=None)
    parser.add_argument("--artifact-mode", type=int, default=None)
    parser.add_argument("--argv", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args(argv)
    with os.fdopen(args.read_fd, "rb", buffering=0) as stream:
        if not gate(stream, args.root, args.ident, graphroot=args.graphroot,
                    deadline=args.deadline,
                    deadline_mono=args.deadline_monotonic,
                    sealed_context=args.context,
                    base=args.base, artifact_sha256=args.artifact_sha256,
                    artifact_mode=args.artifact_mode):
            return 2
    os.execvpe(args.argv[0], args.argv, os.environ.copy())
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
