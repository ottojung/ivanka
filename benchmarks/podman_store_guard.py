"""Optional fail-closed Podman store identity check for physical qualifications.

Only checks a store when both expected settings are supplied. This is an
operational guard, not a new biological qualification criterion.
"""
import subprocess
from pathlib import Path


def verify_expected_store(expected_driver, expected_root, run=subprocess.run):
    """Verify that this process addresses the explicitly selected graph root."""
    if expected_driver is None and expected_root is None:
        return None
    if not expected_driver or not expected_root:
        raise ValueError("Both expected Podman driver and graph root are required")
    if not isinstance(expected_driver, str) or not isinstance(expected_root, str):
        raise ValueError("Invalid expected Podman store identity")
    if not Path(expected_root).is_absolute():
        raise ValueError("Expected Podman graph root must be absolute")
    try:
        root = Path(expected_root).resolve(strict=True)
    except OSError as exc:
        raise ValueError("Expected Podman graph root unavailable") from exc
    if not root.is_dir():
        raise ValueError("Expected Podman graph root is not a directory")
    command = ["podman", "info", "--format",
               "{{.Store.GraphDriverName}}\t{{.Store.GraphRoot}}"]
    try:
        proc = run(command, capture_output=True, text=True,
                   timeout=90, check=True)
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise ValueError("Cannot authenticate expected Podman store") from exc
    lines = proc.stdout.splitlines()
    if len(lines) != 1 or len(lines[0].split("\t")) != 2:
        raise ValueError("Ambiguous Podman graph store evidence")
    actual_driver, actual_root = lines[0].split("\t")
    if actual_driver != expected_driver or Path(actual_root).resolve() != root:
        raise ValueError("Podman store driver or graph root differs from required store")
    return {"driver": actual_driver, "graph_root": str(root)}
