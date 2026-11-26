"""Explicit one-time retry authorization for exhausted PX infrastructure arms.

The ordinary two-attempt infrastructure budget stays fixed. An arm that used
both attempts on infrastructure failures can be dispatched once more only when
an authorization file exists and re-verifies against the exact canonical arm
identity, the indexed terminal receipt bytes, the deployed constant-time guard
pin and the single permitted extra attempt. This module only reads PX evidence
and writes the authorization file; it never launches a process or edits a
receipt, checkpoint, registry or result.
"""
import hashlib
import json
import os
from pathlib import Path

from . import px_cohort_scheduler as sched

SCHEMA = "ivanka.px.retry.authorization.v1"
GUARD_COMMIT = "af1f10d19143fa7a00134a01b56a858ef8a09647"
EXTRA_ATTEMPT = sched.MAX_INFRA_ATTEMPTS + 1
_FIELDS = ("tool_id", "cohort", "alias", "input_sha256", "source_commit",
           "adapter_commit", "image_sha256")


def _json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def authorization_path(root, arm):
    return Path(root) / "authorizations" / (sched.receipt_id(arm) + ".json")


def arm_identity(arm):
    """Copy only the canonical identity fields; reject incomplete callers."""
    if not isinstance(arm, dict) or any(key not in arm for key in _FIELDS):
        raise ValueError("retry arm lacks canonical identity")
    return {key: arm[key] for key in _FIELDS}


def _prior_receipt(root, arm, indexed=None):
    """Read the prior receipt bytes without a recursive verification.

    The preserved attempt is used rather than the canonical receipt because the
    canonical entry advances once the authorized attempt runs. The recorded
    digest is the stable anchor before and after that dispatch; a fresh
    authorization must match the live receipt index as well.
    """
    identifier = sched.receipt_id(arm)
    path = sched.attempt_path(root, arm, sched.MAX_INFRA_ATTEMPTS)
    if not path.is_file():
        raise ValueError("no indexed prior receipt to authorize")
    blob = path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if indexed is None:
        indexed = sched._load_index(root).get(identifier)
    if not isinstance(indexed, str):
        raise ValueError("no indexed prior receipt to authorize")
    if digest != indexed:
        raise ValueError("indexed receipt bytes changed")
    data = json.loads(blob)
    if (data.get("schema") != sched.RECEIPT_SCHEMA
            or data.get("terminal") is not True):
        raise ValueError("indexed receipt is not terminal")
    identity = arm_identity(arm)
    if any(data.get(key) != value for key, value in identity.items()):
        raise ValueError("indexed receipt identity drift")
    return data, indexed


def _preserved_attempts(root, arm):
    """Require both preserved infrastructure-failure receipts to be intact."""
    identity = arm_identity(arm)
    for attempt in range(1, sched.MAX_INFRA_ATTEMPTS + 1):
        path = sched.attempt_path(root, arm, attempt)
        if not path.is_file():
            raise ValueError("preserved attempt receipt is missing")
        data = json.loads(path.read_bytes())
        if (data.get("schema") != sched.RECEIPT_SCHEMA
                or data.get("attempt") != attempt
                or data.get("terminal") is not True
                or any(data.get(key) != value
                       for key, value in identity.items())):
            raise ValueError("preserved attempt receipt drift")
        if (data.get("outcome") != "failure"
                or data.get("failure_reason")
                not in sched.INFRASTRUCTURE_FAILURE_REASONS):
            raise ValueError("preserved attempt is not an infrastructure failure")


def binding(root, arm, prior_digest=None):
    """Build the canonical binding for an exhausted infrastructure arm."""
    receipt, digest = _prior_receipt(root, arm, prior_digest)
    if (receipt.get("outcome") != "failure"
            or receipt.get("failure_reason")
            not in sched.INFRASTRUCTURE_FAILURE_REASONS
            or receipt.get("attempt") != sched.MAX_INFRA_ATTEMPTS):
        raise ValueError("only exhausted infrastructure failure may be authorized")
    _preserved_attempts(root, arm)
    return {"schema": SCHEMA, "arm": arm_identity(arm),
            "prior_receipt_sha256": digest, "guard_commit": GUARD_COMMIT,
            "extra_attempt": EXTRA_ATTEMPT}


def authorize(root, arm):
    """Create the single authorization, or re-verify an identical repeat call."""
    bind = binding(root, arm)
    digest = hashlib.sha256(_json_bytes(bind)).hexdigest()
    payload = _json_bytes(dict(bind, authorization_sha256=digest))
    path = authorization_path(root, arm)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("retry authorization already exists for another binding")
    return path, digest


def verify(root, arm):
    """Return the verified authorization, or None when none was written."""
    path = authorization_path(root, arm)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("retry authorization is unreadable") from exc
    bind = binding(root, arm, record.get("prior_receipt_sha256")
                   if isinstance(record, dict) else None)
    digest = hashlib.sha256(_json_bytes(bind)).hexdigest()
    if (not isinstance(record, dict)
            or record.get("schema") != SCHEMA
            or record.get("authorization_sha256") != digest
            or any(record.get(key) != value for key, value in bind.items())):
        raise ValueError("retry authorization does not bind this arm")
    return record
