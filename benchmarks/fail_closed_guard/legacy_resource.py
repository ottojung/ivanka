"""Read-only attribution of the original host memory guard's exact evidence.

The legacy observable guard (source-pinned a731b560) SIGTERMs an actual MiCall
worker tree above its soft trip and appends a durable event carrying the
space-joined command, observed UTC and resident bytes. A future receipt may
carry the real sampled-resource stop reason only when that event binds to the
same case command and the same durable lease interval. Nothing here changes
the guard, the resource policy, or any retry decision.
"""
import hashlib
import json
import os
import re
from pathlib import Path

from . import lease

SCHEMA = "ivanka.observable-memory-guard.v1"
DEFAULT_LOG = Path("/workspace/micall-frozen-seven-20261117/cap-4gb-memory-violations.jsonl")
LIMIT = 4_000_000_000
TRIP = 3_700_000_000
# The guard replaces every NUL, including the final one, with a space.
PREFIXES = (
    "/opt/venv/bin/python /opt/venv/bin/micall analyze sample ",
    "python /opt/venv/bin/micall analyze sample ",
    "/opt/venv/bin/micall analyze sample ",
)
SUFFIX = " /results --denovo --keep_scratch --all_projects "
READ_1 = re.compile(r"'/reads/([^']*_R1_[^']*\.fastq\.gz)'")


def evidence_path():
    """Project-independent journal, overridable in deterministic tests."""
    return Path(os.environ.get("IVANKA_GUARD_LOG", str(DEFAULT_LOG)))


def read_events(path=None):
    """Return validated legacy guard events; never trust a foreign schema."""
    source = Path(path) if path is not None else evidence_path()
    if source.is_symlink() or not source.is_file():
        return []
    table = []
    for line in source.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("schema") == SCHEMA:
            table.append(event)
    return table


def command_hashes(log_text):
    """Reconstruct the guard's three exact command digests from the bound log."""
    match = READ_1.search(log_text)
    if match is None:
        return set()
    read_1 = "/reads/" + match.group(1)
    read_2 = read_1.replace("_R1_", "_R2_")
    return {hashlib.sha256((prefix + read_1 + " " + read_2 + SUFFIX).encode()).hexdigest()
            for prefix in PREFIXES}


def attributed_resource_stop(root, ident, log_path, *, path=None):
    """Return ``observed_rss_limit`` only on exact command/lease/timestamp proof.

    The command digest must come from this arm's hash-bound log, the violation
    time must fall inside this arm's durable lease interval, and the guard must
    have observed at least its soft-trip resident bytes. An absent, foreign or
    ambiguous match returns None and leaves the receipt reason untouched.
    """
    hashes = command_hashes(Path(log_path).read_text(errors="replace"))
    if not hashes:
        return None
    try:
        journal = lease.events(root)
    except (OSError, ValueError):
        return None
    mine = [event for event in journal if event.get("lease") == str(ident)]
    starts = [event["at_utc"] for event in mine
              if event.get("state") == "active"
              and isinstance(event.get("at_utc"), (int, float))]
    closes = [event["at_utc"] for event in mine
              if event.get("state") in lease.CLOSED
              and isinstance(event.get("at_utc"), (int, float))]
    if not starts:
        return None
    lower, upper = min(starts), max(closes) if closes else float("inf")
    for event in read_events(path):
        at, resident = event.get("observed_utc"), event.get("rss_tree_bytes")
        if (event.get("command_sha256") in hashes
                and event.get("action") in ("SIGTERM", "SIGKILL")
                and isinstance(at, (int, float))
                and isinstance(resident, (int, float)) and resident >= TRIP
                and lower - 1 <= at <= upper + 5):
            return "observed_rss_limit"
    return None
