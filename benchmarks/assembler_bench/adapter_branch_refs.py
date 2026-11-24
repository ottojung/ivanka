"""Offline reproducible, exact-commit MiCall fork ref observations."""
import json
import re
from pathlib import Path

REFS = Path(__file__).with_suffix(".json")
FORK = "https://github.com/ottojung/MiCall"


def branch_for(tool, commit):
    """Never substitute a similarly named branch or a different commit."""
    record = json.loads(REFS.read_text())
    if record.get("fork") != FORK:
        raise ValueError("adapter branch observation fork mismatch")
    pin = record["pins"].get(commit, {})
    branch = pin.get("branch", "")
    if (pin.get("id") != tool
            or not re.fullmatch(r"bench/[A-Za-z0-9_./-]+", branch)):
        raise ValueError("missing verified adapter branch for " + tool
                         + " at " + str(commit))
    return branch


def adapter_provenance(tool, commit):
    return {"source_branch": branch_for(tool, commit),
            "source_url": FORK + "/tree/" + commit}
