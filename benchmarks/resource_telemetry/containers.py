"""Discover the exact Podman worker PIDs without using shared-cgroup stats."""
import subprocess


def call(args):
    return subprocess.run(["podman", *args], capture_output=True,
                          text=True, timeout=15, check=True).stdout


def running():
    """Return ID, container name and initial process ID for live benchmark arms."""
    listing = call(["ps", "--format", "{{.ID}} {{.Names}}"])
    rows = [line.split(maxsplit=1) for line in listing.splitlines()]
    rows = [(cid, name) for cid, name in rows
            if name.startswith(("ivanka-bench-ivanka-", "ivanka-bench-iva-",
                                "ivanka-bench-synth-"))]
    if not rows:
        return {}
    # A container can exit between listing and inspection. In that case
    # preserve the last known readings and retry discovery next cycle.
    output = call(["inspect", "--format", "{{.State.Pid}}",
                   *[cid for cid, _ in rows]]).splitlines()
    if len(output) != len(rows):
        raise ValueError("Podman inspection returned incomplete PID list")
    return {cid: (name, int(pid)) for (cid, name), pid
            in zip(rows, output) if int(pid) > 0}
