"""Discover benchmark PIDs from one Podman listing, not contended inspect."""
import subprocess


def call(args):
    return subprocess.run(["podman", *args], capture_output=True,
                          text=True, timeout=15, check=True).stdout


def decode(listing):
    """Return live bench worker IDs, names and positive host PIDs."""
    found = {}
    for line in listing.splitlines():
        cells = line.split(maxsplit=2)
        if len(cells) != 3:
            raise ValueError("invalid Podman process listing row")
        cid, name, raw_pid = cells
        if not name.startswith(("ivanka-bench-ivanka-",
                                "ivanka-bench-iva-",
                                "ivanka-bench-synth-")):
            continue
        if (len(cid) not in (12, 64)
                or any(x not in "0123456789abcdef" for x in cid)):
            raise ValueError("invalid benchmark container ID")
        pid = int(raw_pid)
        if pid <= 0:
            continue
        if cid in found:
            raise ValueError("duplicate benchmark container ID")
        found[cid] = (name, pid)
    return found


def running():
    """One database transaction avoids inspect races and lock contention."""
    return decode(call(["ps", "--format", "{{.ID}} {{.Names}} {{.Pid}}"]))
