"""Read conservative resident-byte totals for each benchmark MiCall tree."""
from pathlib import Path

LIMIT = 4_000_000_000
TRIP = 3_700_000_000
ROOT = Path("/proc")


def processes(root=ROOT):
    result = {}
    for folder in root.iterdir():
        if not folder.name.isdecimal():
            continue
        try:
            status = (folder / "status").read_text().splitlines()
            values = dict(line.split(":", 1) for line in status if ":" in line)
            ppid = int(values["PPid"].strip())
            resident = int(values.get("VmRSS", "0 kB").strip().split()[0]) * 1024
            args = (folder / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                errors="replace")
        except (OSError, KeyError, ValueError):
            continue
        result[int(folder.name)] = (ppid, resident, args)
    return result


def benchmark_roots(table):
    """Actual MiCall processes, excluding Podman CLI and timing wrappers."""
    prefixes = (
        "/opt/venv/bin/python /opt/venv/bin/micall analyze sample ",
        "python /opt/venv/bin/micall analyze sample ",
        "/opt/venv/bin/micall analyze sample ",
    )
    return {pid for pid, (_, _, args) in table.items()
            if args.startswith(prefixes)
            and ("/bench/samples/" in args or "/reads/" in args)}


def tree_bytes(table, root):
    members = {root}
    while True:
        children = {pid for pid, (ppid, _, _) in table.items() if ppid in members}
        if children <= members:
            break
        members |= children
    return sum(table[pid][1] for pid in members if pid in table), members
