"""Explicit one-time retry authorization for exhausted PX infrastructure arms.

The ordinary two-attempt infrastructure budget stays fixed. An arm that used
both attempts on infrastructure failures can be dispatched once more only when
an authorization file exists and re-verifies against the exact canonical arm
identity, every preserved prior-attempt receipt, the indexed terminal receipt
bytes, the deployed guard source digest and the single permitted extra attempt.
The authorization is consumed by an exclusive, durable dispatch marker *before*
any process is spawned, so an interrupted dispatch can never be re-run against
the same one-shot authorization. This module only reads PX evidence and writes
authorization/marker files; it never launches a process or edits a receipt,
checkpoint, registry or result.
"""
import hashlib
import json
import os
from pathlib import Path

from . import px_cohort_scheduler as sched
from . import px_guard_source as guard_source

SCHEMA = "ivanka.px.retry.authorization.v1"
DISPATCH_SCHEMA = "ivanka.px.retry.dispatch.v1"
# Kept as the reviewed commit identity; the source digest below is what the
# authorization actually verifies at run time.
GUARD_COMMIT = guard_source.GUARD_COMMIT
EXTRA_ATTEMPT = sched.MAX_INFRA_ATTEMPTS + 1
_FIELDS = ("tool_id", "cohort", "alias", "input_sha256", "source_commit",
           "adapter_commit", "image_sha256")


def _json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fsync_dir(path):
    directory = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def authorization_path(root, arm):
    return Path(root) / "authorizations" / (sched.receipt_id(arm) + ".json")


def dispatch_path(root, arm):
    """The durable, exclusive one-shot consumption marker for this arm."""
    return authorization_path(root, arm).with_name(
        sched.receipt_id(arm) + ".dispatched.json")


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
    """Digest and validate every preserved infrastructure-failure attempt.

    Binding only the last receipt would let an earlier preserved attempt drift
    without invalidating the authorization, so the digest of each attempt is
    returned and included in the canonical binding.
    """
    identity = arm_identity(arm)
    digests = {}
    for attempt in range(1, sched.MAX_INFRA_ATTEMPTS + 1):
        path = sched.attempt_path(root, arm, attempt)
        if not path.is_file():
            raise ValueError("preserved attempt receipt is missing")
        blob = path.read_bytes()
        data = json.loads(blob)
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
        digests[str(attempt)] = hashlib.sha256(blob).hexdigest()
    return digests


def binding(root, arm, prior_digest=None):
    """Build the canonical binding for an exhausted infrastructure arm."""
    receipt, digest = _prior_receipt(root, arm, prior_digest)
    if (receipt.get("outcome") != "failure"
            or receipt.get("failure_reason")
            not in sched.INFRASTRUCTURE_FAILURE_REASONS
            or receipt.get("attempt") != sched.MAX_INFRA_ATTEMPTS):
        raise ValueError("only exhausted infrastructure failure may be authorized")
    preserved = _preserved_attempts(root, arm)
    # Re-derive the deployed guard identity instead of trusting a constant.
    guard = guard_source.verify()
    return {"schema": SCHEMA, "arm": arm_identity(arm),
            "prior_receipt_sha256": digest,
            "preserved_attempt_sha256": preserved,
            "guard_commit": GUARD_COMMIT,
            "guard_source_sha256": guard[guard_source.RESERVE_SOURCE],
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
    _fsync_dir(path.parent)
    return path, digest


def _verified_record(root, arm):
    """Verify authorization bytes against live evidence; None when absent."""
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


def verify(root, arm):
    """Return the still-available authorization, or None if absent/consumed."""
    record = _verified_record(root, arm)
    if record is None or dispatch_path(root, arm).exists():
        return None
    return record


def claim(root, arm):
    """Consume the one-shot authorization before a process is spawned.

    The exclusive create is fsynced before returning, so a dispatched arm that
    is interrupted before recording a receipt can never be dispatched again
    under the same authorization. A changed or duplicated marker fails closed.
    """
    path = dispatch_path(root, arm)
    if path.exists():
        raise ValueError("retry authorization was already consumed")
    record = verify(root, arm)
    if record is None:
        raise ValueError("retry authorization is not available")
    payload = _json_bytes({
        "schema": DISPATCH_SCHEMA,
        "authorization_sha256": record["authorization_sha256"],
        "extra_attempt": EXTRA_ATTEMPT,
    })
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("retry authorization was already consumed") from exc
    _fsync_dir(path.parent)
    return path


def verify_spent(root, arm):
    """Return the authorization only when consumed by the one extra dispatch.

    A terminal extra-attempt receipt is valid only if the dispatch was claimed
    first; this distinguishes an authorized run from a receipt written without
    pre-spawn consumption.
    """
    record = _verified_record(root, arm)
    if record is None:
        return None
    path = dispatch_path(root, arm)
    if not path.is_file():
        return None
    try:
        marker = json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("retry dispatch marker is unreadable") from exc
    if (not isinstance(marker, dict)
            or marker.get("schema") != DISPATCH_SCHEMA
            or marker.get("authorization_sha256") != record["authorization_sha256"]
            or marker.get("extra_attempt") != EXTRA_ATTEMPT):
        raise ValueError("retry dispatch marker does not bind authorization")
    return record
