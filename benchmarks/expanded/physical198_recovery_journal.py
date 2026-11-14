"""Read one original MiCall invocation without suppressing partial outcomes."""
import hashlib
import json
from pathlib import Path


def read_journal(file, allowed):
    raw = Path(file).read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("missing or unterminated source journal")
    seen, completed, invocations = set(), {}, set()
    for line in raw.splitlines():
        event = json.loads(line)
        name, status, invocation = (
            event.get("sample"), event.get("status"), event.get("invocation"))
        if name not in allowed or not isinstance(invocation, str) or not invocation:
            raise ValueError("unrecognized sample or invocation")
        invocations.add(invocation)
        if status == "started":
            if name in seen:
                raise ValueError("duplicate or out-of-order start")
            seen.add(name)
        elif status == "finished":
            if name not in seen or name in completed:
                raise ValueError("unmatched or duplicated terminal")
            if event.get("failed") is not False:
                raise ValueError("failed terminal cannot be reused")
            completed[name] = event
        else:
            raise ValueError("non-successful or substituted execution event")
    if len(invocations) != 1:
        raise ValueError("mixed invocations in source journal")
    return {
        "finished": completed, "started": seen,
        "unclosed": seen - set(completed),
        "invocation": next(iter(invocations)),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def combine(original, recovered, expected, missing):
    """Never hide a failed event or a duplicate successful sample."""
    if set(original["finished"]) & set(recovered["finished"]):
        raise ValueError("duplicate completed samples between source invocations")
    if original["invocation"] == recovered["invocation"]:
        raise ValueError("recovery must be separately identified")
    if not original["unclosed"] <= missing:
        raise ValueError("unclosed source case excluded from recovery")
    if (set(recovered["started"]) != missing
            or recovered["unclosed"]
            or set(recovered["finished"]) != missing):
        raise ValueError("recovery missing selected original samples")
    if set(original["finished"]) | set(recovered["finished"]) != expected:
        raise ValueError("incomplete physical cohort")
    return {**original["finished"], **recovered["finished"]}
